import type { ParcelBoundingBox, ParcelPosition } from "@/types/config";

export interface ValidateResponse {
  valid: boolean;
  errors: string[];
}

export type PartialValidationStep = "parcel" | "sensors" | "telemetry" | "objective";

export interface ProvinciaOption {
  id: string;
  nombre: string;
}

export interface MunicipioOption {
  id: string;
  nombre: string;
  provinciaId: string;
}


export interface MunicipioViewportResponse {
  found: boolean;
  bbox: ParcelBoundingBox | null;
  centroid: ParcelPosition | null;
  source: string | null;
}


export interface TelemetryExtractRequest {
  features: string[];
  punto: { lat: number; lng: number } | null;
  startDate: string;
  endDate: string;
  cloudThreshold: number;
}

export interface TelemetryPoint {
  date: string;
  values: Record<string, number>;
  cloudCover: number | null;
}

export interface TelemetryExtractResponse {
  success: boolean;
  errors: string[];
  collection: string | null;
  indices: string[];
  startDate: string | null;
  endDate: string | null;
  imageCount: number;
  points: TelemetryPoint[];
}

export interface SatisfiableResponse {
  satisfiable: boolean;
}

export interface ConfigurationsNumberResponse {
  configurationsNumber: number;
}

export interface DeadFeaturesResponse {
  deadFeatures: string[];
}

// ------------------------------------------------------------------ feature model

export type FeatureRelationType = "MANDATORY" | "ALTERNATIVE" | "OR" | "OPTIONAL";

export interface FeatureRelation {
  type: FeatureRelationType;
  children: FeatureModelNode[];
}

export interface ConstraintAST {
  op: "FEATURE" | "IMPLIES" | "OR" | "AND" | "NOT";
  name?: string;
  left?: ConstraintAST;
  right?: ConstraintAST;
}

export interface FeatureConstraint {
  features: string[];
  ast: ConstraintAST;
}

export interface FeatureModelNode {
  name: string;
  relations: FeatureRelation[];
  attributes?: Record<string, string | number | boolean>;
  constraints?: FeatureConstraint[];
}

export interface ValidateFeaturesRequest {
  features: string[];
  is_full: boolean;
  step?: PartialValidationStep | "full";
}

// ------------------------------------------------------------------ modelos

export interface TrainStartResponse {
  model_id: string;
  status: string;
}

export interface TargetMetrics {
  mae: number;
  rmse: number;
  r2: number;
}

export interface ValSeries {
  y_true: number[];
  y_pred: number[];
}

export interface TrainingStatus {
  status: "training" | "completed" | "error";
  phase?: string | null;
  algorithm?: string | null;
  current_epoch?: number | null;
  total_epochs?: number | null;
  current_target?: string | null;
  val_loss?: number | null;
  n_train?: number | null;
  n_val?: number | null;
  metrics?: Record<string, TargetMetrics>;
  val_series?: Record<string, ValSeries>;
  warnings?: string[];
  detail?: string | null;
  // campos adicionales cuando status === "completed" (vienen del metadata)
  model_id?: string;
  treatment?: string;
  targets?: string[];
  n_samples?: number;
}

export interface PredictionHistoryItem {
  prediction_id: number;
  model_id: string;
  generated_at: string;
  predicted_for_date: string;
  predictions: Record<string, number>;
  input_row_count: number;
  warnings: string[];
}

export type PredictionResponse = PredictionHistoryItem;

// ------------------------------------------------------------------ configuraciones guardadas

export interface Configuracion {
  id: number;
  nombre: string;
  features: string[];
  geo: Record<string, unknown>;
  uvl_version: number | null;
  is_obsolete: boolean;
  obsolete_reason: string;
  created_at: string;
  updated_at: string;
}

// ------------------------------------------------------------------ UVL versioning

export interface UVLVersionSummary {
  id: number;
  name: string;
  description: string;
  file_hash: string;
  author_username: string | null;
  created_at: string;
  is_active: boolean;
  is_valid: boolean;
  validation_errors: string[];
}

export interface UVLVersionDetail extends UVLVersionSummary {
  tree: FeatureModelNode | null;
}

export interface UVLValidateResponse {
  valid: boolean;
  errors: string[];
}

export interface UVLPreviewActivationReport {
  total: number;
  affected: { id: number; nombre: string; user: string; reason: string }[];
  error?: string;
}

export interface UVLActivateResponse {
  detail: string;
  report: UVLPreviewActivationReport | null;
}

// ------------------------------------------------------------------ usuarios

export interface AuthUser {
  id: number;
  email: string;
  nombre: string;
  role: "tecnico" | "administrador";
  is_active: boolean;
  date_joined: string;
}

export interface ModelMetadata {
  model_id: string;
  algorithm: string;
  treatment: string;
  features?: string[];
  geo?: Record<string, unknown> & {
    punto?: { lat: number; lng: number } | null;
    cloudThreshold?: number;
  };
  all_cols: string[];
  targets: string[];
  input_features: string[];
  window_size: number;
  n_samples: number;
  n_train: number;
  n_val: number;
  metrics: Record<string, TargetMetrics>;
  warnings: string[];
  imported?: boolean;
  created_at?: string;
}
