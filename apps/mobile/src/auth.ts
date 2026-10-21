import * as AuthSession from "expo-auth-session";
import * as SecureStore from "expo-secure-store";
import * as WebBrowser from "expo-web-browser";
WebBrowser.maybeCompleteAuthSession();
const key = "agrovision.oidc.refresh";
const issuer = process.env.EXPO_PUBLIC_OIDC_ISSUER ?? "";
const clientId = process.env.EXPO_PUBLIC_OIDC_CLIENT_ID ?? "";
export const authMode =
  process.env.EXPO_PUBLIC_AUTH_MODE === "development" ? "development" : "oidc";
export async function signInOidc() {
  if (!issuer || !clientId)
    throw Error("Настройте OIDC issuer и client ID перед входом.");
  const discovery = await AuthSession.fetchDiscoveryAsync(issuer);
  const redirectUri = AuthSession.makeRedirectUri({ scheme: "agrovision" });
  const request = new AuthSession.AuthRequest({
    clientId,
    redirectUri,
    scopes: ["openid", "profile", "offline_access"],
    responseType: AuthSession.ResponseType.Code,
    usePKCE: true,
  });
  const response = await request.promptAsync(discovery);
  if (response.type !== "success") return null;
  const tokens = await AuthSession.exchangeCodeAsync(
    {
      clientId,
      code: response.params.code,
      redirectUri,
      extraParams: { code_verifier: request.codeVerifier! },
    },
    discovery,
  );
  if (tokens.refreshToken)
    await SecureStore.setItemAsync(key, tokens.refreshToken);
  return tokens.accessToken;
}
export async function restoreOidc() {
  const token = await SecureStore.getItemAsync(key);
  if (!token || !issuer || !clientId) return null;
  try {
    const tokens = await AuthSession.refreshAsync(
      { clientId, refreshToken: token },
      await AuthSession.fetchDiscoveryAsync(issuer),
    );
    if (tokens.refreshToken)
      await SecureStore.setItemAsync(key, tokens.refreshToken);
    return tokens.accessToken;
  } catch {
    await SecureStore.deleteItemAsync(key);
    return null;
  }
}
export async function clearSession() {
  const token = await SecureStore.getItemAsync(key);
  await SecureStore.deleteItemAsync(key);
  if (token && issuer && clientId) {
    try {
      await AuthSession.revokeAsync(
        { clientId, token },
        await AuthSession.fetchDiscoveryAsync(issuer),
      );
    } catch {
      /* Local session is cleared even if issuer is offline. */
    }
  }
}
