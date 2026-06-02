import { describe, it, expect } from "vitest";
import { cn } from "@/lib/utils";

describe("cn", () => {
  it("joins simple class names", () => {
    expect(cn("a", "b")).toBe("a b");
  });

  it("strips falsy values", () => {
    expect(cn("a", null, undefined, false, "b")).toBe("a b");
  });

  it("dedupes tailwind utilities", () => {
    expect(cn("p-2", "p-4")).toBe("p-4");
  });
});
