import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "dist",
      "node_modules",
      "coverage",
      "e2e/playwright-report",
      "e2e/test-results",
    ],
  },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],
    },
  },
  {
    // Playwright E2E suite — Node + Playwright context, no React rules apply.
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["e2e/**/*.ts"],
    languageOptions: {
      ecmaVersion: 2020,
      globals: { ...globals.node },
    },
  },
);
