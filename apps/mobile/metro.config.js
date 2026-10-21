const { getDefaultConfig } = require("expo/metro-config");
const config = getDefaultConfig(__dirname);
// Keep local Android builds within the shared workstation's memory budget.
config.maxWorkers = 1;
module.exports = config;
