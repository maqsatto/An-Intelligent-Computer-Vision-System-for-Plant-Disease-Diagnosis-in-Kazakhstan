export default {
  expo: {
    name: "AgroVision",
    slug: "agrovision",
    version: "0.1.0",
    orientation: "portrait",
    userInterfaceStyle: "light",
    scheme: "agrovision",
    platforms: ["android", "ios"],
    android: { package: "kz.agrovision.mobile", permissions: ["CAMERA"] },
    plugins: [
      [
        "expo-image-picker",
        {
          photosPermission: "Выберите фото листа для наблюдения.",
          cameraPermission: "Снимите лист для наблюдения.",
          microphonePermission: false,
        },
      ],
      [
        "./plugins/withDevelopmentNetwork",
        { enabled: process.env.EXPO_PUBLIC_AUTH_MODE === "development" },
      ],
      "expo-secure-store",
      "expo-web-browser",
    ],
    extra: { eas: {} },
  },
};
