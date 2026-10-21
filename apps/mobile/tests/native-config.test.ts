import { test } from "node:test";
import assert from "node:assert/strict";
const plugin = require("../plugins/withDevelopmentNetwork");
test("native HTTP access is disabled by default and enabled only for explicit development", async () => {
  for (const enabled of [undefined, false, true]) {
    const config = plugin({ name: "test", slug: "test" }, { enabled });
    const output = await config.mods.android.manifest({
      ...config,
      modResults: { manifest: { application: [{ $: {} }] } },
      modRequest: {
        projectRoot: process.cwd(),
        platformProjectRoot: process.cwd(),
        platform: "android",
        modName: "manifest",
        introspect: true,
      },
    });
    assert.equal(
      output.modResults.manifest.application[0].$[
        "android:usesCleartextTraffic"
      ],
      enabled === true ? "true" : "false",
    );
  }
});
