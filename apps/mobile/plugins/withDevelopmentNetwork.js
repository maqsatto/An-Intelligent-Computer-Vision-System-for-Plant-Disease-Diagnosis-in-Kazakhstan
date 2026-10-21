const { withAndroidManifest } = require("expo/config-plugins");
module.exports = function withDevelopmentNetwork(
  config,
  { enabled = false } = {},
) {
  return withAndroidManifest(config, (config) => {
    const application = config.modResults.manifest.application?.[0];
    if (application)
      application.$["android:usesCleartextTraffic"] = enabled
        ? "true"
        : "false";
    return config;
  });
};
