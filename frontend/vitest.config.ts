import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react-swc";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    globals: true,
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      include: [
        "src/lib/**/*.ts",
        "src/utils/**/*.ts",
        "src/services/**/*.ts",
        "src/contexts/**/*.tsx",
      ],
      exclude: ["src/**/*.test.*", "src/**/__tests__/**"],
      thresholds: {
        lines: 75,
        statements: 75,
        functions: 65,
        branches: 60,
      },
    },
  },
});
