module.exports = {
  root: true,
  env: {
    browser: true,
    es2022: true,
  },
  parserOptions: {
    ecmaVersion: "latest",
    sourceType: "script",
  },
  ignorePatterns: ["app/static/js/lucide.min.js"],
  overrides: [
    {
      files: [
        "app/static/js/dashboard-page.js",
        "app/static/js/integrations-page.js",
      ],
      rules: {
        "no-eval": "error",
        "no-implied-eval": "error",
        "no-new-func": "error",
        "no-script-url": "error",
        "no-alert": "off",
      },
    },
  ],
};
