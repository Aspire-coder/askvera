# Themes

The theme system lives in:

```text
src/themes/
```

It supports:

- light mode
- dark mode
- custom themes
- runtime theme switching
- CSS variable output

## Theme Tokens

Theme tokens include:

- colors
- typography
- spacing
- radius
- shadows
- layout sizes
- motion

## Runtime Usage

```ts
AskVera.updateConfig({
  theme: {
    mode: "dark"
  }
});
```

## Custom Brand Example

```ts
AskVera.updateConfig({
  theme: {
    mode: "custom",
    colors: {
      accent: "#ffc400",
      headerBg: "#000000",
      headerText: "#ffffff"
    }
  }
});
```

Components should consume theme variables and avoid hardcoded brand styling.

