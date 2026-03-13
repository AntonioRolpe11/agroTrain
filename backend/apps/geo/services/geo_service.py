from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _Provincia:
    id: str
    nombre: str


_PROVINCIAS: tuple[_Provincia, ...] = (
    _Provincia("01", "Araba/Alava"),
    _Provincia("02", "Albacete"),
    _Provincia("03", "Alicante/Alacant"),
    _Provincia("04", "Almeria"),
    _Provincia("05", "Avila"),
    _Provincia("06", "Badajoz"),
    _Provincia("07", "Balears, Illes"),
    _Provincia("08", "Barcelona"),
    _Provincia("09", "Burgos"),
    _Provincia("10", "Caceres"),
    _Provincia("11", "Cadiz"),
    _Provincia("12", "Castellon/Castello"),
    _Provincia("13", "Ciudad Real"),
    _Provincia("14", "Cordoba"),
    _Provincia("15", "Coruna, A"),
    _Provincia("16", "Cuenca"),
    _Provincia("17", "Girona"),
    _Provincia("18", "Granada"),
    _Provincia("19", "Guadalajara"),
    _Provincia("20", "Gipuzkoa"),
    _Provincia("21", "Huelva"),
    _Provincia("22", "Huesca"),
    _Provincia("23", "Jaen"),
    _Provincia("24", "Leon"),
    _Provincia("25", "Lleida"),
    _Provincia("26", "Rioja, La"),
    _Provincia("27", "Lugo"),
    _Provincia("28", "Madrid"),
    _Provincia("29", "Malaga"),
    _Provincia("30", "Murcia"),
    _Provincia("31", "Navarra"),
    _Provincia("32", "Ourense"),
    _Provincia("33", "Asturias"),
    _Provincia("34", "Palencia"),
    _Provincia("35", "Palmas, Las"),
    _Provincia("36", "Pontevedra"),
    _Provincia("37", "Salamanca"),
    _Provincia("38", "Santa Cruz de Tenerife"),
    _Provincia("39", "Cantabria"),
    _Provincia("40", "Segovia"),
    _Provincia("41", "Sevilla"),
    _Provincia("42", "Soria"),
    _Provincia("43", "Tarragona"),
    _Provincia("44", "Teruel"),
    _Provincia("45", "Toledo"),
    _Provincia("46", "Valencia/Valencia"),
    _Provincia("47", "Valladolid"),
    _Provincia("48", "Bizkaia"),
    _Provincia("49", "Zamora"),
    _Provincia("50", "Zaragoza"),
    _Provincia("51", "Ceuta"),
    _Provincia("52", "Melilla"),
)

_PROVINCIAS_BY_ID: dict[str, _Provincia] = {prov.id: prov for prov in _PROVINCIAS}


class GeoCatalogError(RuntimeError):
    pass


class GeoService:
    MUNICIPIOS_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "municipios.json"

    def get_provincias(self) -> list[dict[str, str]]:
        return [{"id": prov.id, "nombre": prov.nombre} for prov in _PROVINCIAS]

    def get_municipios(self, provincia_id: str) -> list[dict[str, str]]:
        municipios = [m for m in self._load_municipios() if m["provinciaId"] == provincia_id]
        return sorted(municipios, key=lambda m: m["nombre"].casefold())

    def get_municipio_viewport(self, provincia_id: str, municipio_id: str) -> dict[str, Any]:
        provincia = _PROVINCIAS_BY_ID.get(provincia_id)
        if provincia is None:
            raise GeoCatalogError("La provincia seleccionada no existe en el catálogo geográfico.")

        municipio = self._municipios_by_id().get(municipio_id)
        if municipio is None:
            raise GeoCatalogError("El municipio seleccionado no existe en el catálogo geográfico.")
        if municipio["provinciaId"] != provincia_id:
            raise GeoCatalogError("El municipio seleccionado no pertenece a la provincia indicada.")

        viewport = self._geocode_municipio_bounds(municipio["nombre"], provincia.nombre)
        if viewport is None:
            return {"found": False}

        return {
            "found": True,
            "bbox": viewport["bbox"],
            "centroid": viewport["centroid"],
            "source": "nominatim",
        }

    @staticmethod
    @lru_cache(maxsize=1)
    def _load_municipios() -> tuple[dict[str, str], ...]:
        try:
            payload = json.loads(GeoService.MUNICIPIOS_DATA_PATH.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise GeoCatalogError("No se encontró el catálogo local de municipios.") from exc
        except json.JSONDecodeError as exc:
            raise GeoCatalogError("El catálogo local de municipios no es válido.") from exc

        if not isinstance(payload, list) or not payload:
            raise GeoCatalogError("El catálogo local de municipios no contiene datos utilizables.")

        municipios: list[dict[str, str]] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            municipio_id = str(row.get("id", ""))
            provincia_id = str(row.get("provinciaId", ""))
            nombre = str(row.get("nombre", ""))
            if len(municipio_id) != 5 or len(provincia_id) != 2 or not nombre:
                continue
            municipios.append({"id": municipio_id, "nombre": nombre, "provinciaId": provincia_id})

        if not municipios:
            raise GeoCatalogError("No fue posible extraer municipios del catálogo oficial.")

        unique: dict[str, dict[str, str]] = {}
        for m in municipios:
            unique[m["id"]] = m
        return tuple(unique.values())

    @classmethod
    @lru_cache(maxsize=1)
    def _municipios_by_id(cls) -> dict[str, dict[str, str]]:
        return {m["id"]: m for m in cls._load_municipios()}

    @staticmethod
    @lru_cache(maxsize=2048)
    def _geocode_municipio_bounds(
        municipio_nombre: str,
        provincia_nombre: str,
    ) -> dict[str, tuple[float, ...]] | None:
        params = urlencode({
            "format": "jsonv2",
            "limit": 1,
            "countrycodes": "es",
            "q": f"{municipio_nombre}, {provincia_nombre}, Spain",
        })
        url = f"https://nominatim.openstreetmap.org/search?{params}"
        request = Request(url, headers={"User-Agent": "agroTrain/1.0 (parcel-viewport)"})

        try:
            with urlopen(request, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            logger.warning("Nominatim geocoding failed for '%s, %s'", municipio_nombre, provincia_nombre)
            return None

        if not isinstance(payload, list) or not payload:
            return None

        row = payload[0]
        if not isinstance(row, dict):
            return None

        bbox = row.get("boundingbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            return None

        try:
            south, north, west, east = (float(bbox[i]) for i in range(4))
        except (TypeError, ValueError):
            return None

        centroid = ((west + east) / 2.0, (south + north) / 2.0)
        return {
            "bbox": (round(west, 8), round(south, 8), round(east, 8), round(north, 8)),
            "centroid": (round(centroid[0], 8), round(centroid[1], 8)),
        }
