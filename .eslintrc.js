module.exports = {
  extends: ['alloy', 'alloy/react', 'alloy/typescript', 'plugin:prettier/recommended'],
  parserOptions: {
    project: './tsconfig.json',
    tsconfigRootDir: __dirname,
  },
  settings: {
    react: {
      version: 'detect',
    },
  },
  env: {
    // 你的环境变量（包含多个预定义的全局变量）
    //
    // browser: true,
    // node: true,
    // mocha: true,
    // jest: true,
    // jquery: true
  },
  globals: {
    // 你的全局变量（设置为 false 表示它不允许被重新赋值）
    //
    // myGlobal: false
  },
  rules: {
    // 自定义你的规则
    // 最大圈复杂度
    complexity: ['error', 30],
    'linebreak-style': 'off',
    'prettier/prettier': 'off',
    'max-params': 'off',
    '@typescript-eslint/member-ordering': 'off',
    '@typescript-eslint/prefer-optional-chain': 'warn',
    'no-void': 'off',
    'prefer-object-has-own': 'off',
    semi: 2,
    // indent: ['error', 2],
    'semi-style': ['error', 'last'],
    'react/jsx-no-useless-fragment': [
      'error',
      {
        allowExpressions: true,
      },
    ],
  },
};
