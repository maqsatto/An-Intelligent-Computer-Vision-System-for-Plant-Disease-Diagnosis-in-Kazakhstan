import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ActivityIndicator,
  Alert,
  AppState,
  BackHandler,
  Image,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import {
  MD3LightTheme,
  PaperProvider,
  BottomNavigation,
} from "react-native-paper";
import * as ImagePicker from "expo-image-picker";
import * as ImageManipulator from "expo-image-manipulator";
import * as Crypto from "expo-crypto";
import { ApiClient, ApiError, type Schemas } from "@agrovision/api-client";
import { authMode, clearSession, restoreOidc, signInOidc } from "./auth";
import {
  conditionLabel,
  delay,
  outcomeCopy,
  pollAssessment,
  reasons,
  runSubmission,
  type Draft,
} from "./flow";
const C = {
  background: "#f6f7f2",
  surface: "#ffffff",
  brand: "#174c38",
  action: "#267a51",
  text: "#182a20",
  muted: "#647369",
  tint: "#e5f1e9",
  border: "#dce5dd",
  warning: "#fff1d2",
  danger: "#9c382f",
};
const theme = {
  ...MD3LightTheme,
  colors: {
    ...MD3LightTheme.colors,
    primary: C.brand,
    secondaryContainer: C.tint,
    surface: C.surface,
    onSurface: C.text,
    onSurfaceVariant: C.muted,
  },
};
type Screen =
  | "home"
  | "crops"
  | "capture"
  | "preview"
  | "progress"
  | "result"
  | "history"
  | "login";
type Crop = Schemas["CatalogRead"]["crops"][number];
function Button({
  label,
  onPress,
  secondary = false,
  disabled = false,
}: {
  label: string;
  onPress: () => void;
  secondary?: boolean;
  disabled?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        s.button,
        secondary && s.secondary,
        disabled && { opacity: 0.45 },
        pressed && { opacity: 0.75 },
      ]}
    >
      <Text style={[s.buttonText, secondary && { color: C.brand }]}>
        {label}
      </Text>
    </Pressable>
  );
}
function Notice({
  title,
  body,
  warning = false,
}: {
  title: string;
  body?: string;
  warning?: boolean;
}) {
  return (
    <View style={[s.notice, warning && { backgroundColor: C.warning }]}>
      <Text style={s.label}>{title}</Text>
      {body && <Text style={s.body}>{body}</Text>}
    </View>
  );
}
function Heading({ title, body }: { title: string; body?: string }) {
  return (
    <>
      <Text accessibilityRole="header" style={s.heading}>
        {title}
      </Text>
      {body && <Text style={s.muted}>{body}</Text>}
    </>
  );
}
function AppContent() {
  const [screen, setScreen] = useState<Screen>("home");
  const [token, setToken] = useState<string | null>(null);
  const tokenRef = useRef(token);
  tokenRef.current = token;
  const api = useMemo(
    () =>
      new ApiClient(
        process.env.EXPO_PUBLIC_API_URL ?? "http://10.0.2.2:8000",
        () => tokenRef.current,
      ),
    [],
  );
  const [catalog, setCatalog] = useState<Schemas["CatalogRead"] | null>(null);
  const [actor, setActor] = useState<Schemas["MeRead"] | null>(null);
  const [crop, setCrop] = useState<Crop | null>(null);
  const [history, setHistory] = useState<Schemas["ObservationRead"][]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [assessment, setAssessment] = useState<
    Schemas["AssessmentRead"] | null
  >(null);
  const [observation, setObservation] = useState<
    Schemas["ObservationRead"] | null
  >(null);
  const [image, setImage] = useState<{
    uri: string;
    headers?: Record<string, string>;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState("");
  const [error, setError] = useState("");
  const [operatorToken, setOperatorToken] = useState("");
  const [feedback, setFeedback] = useState("");
  const [feedbackSent, setFeedbackSent] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const active = useRef<AbortController | null>(null);
  const sessionEpoch = useRef(0);
  const submitLock = useRef(false);
  const newAttempt = useRef<{ source: string; key: string } | null>(null);
  const stop = useCallback(() => {
    active.current?.abort();
    active.current = null;
  }, []);
  const navigate = useCallback(
    (next: Screen) => {
      stop();
      setError("");
      setScreen(next);
    },
    [stop],
  );
  const handleError = useCallback(
    (e: unknown) => {
      if ((e as Error)?.name === "AbortError") return;
      const a = e as ApiError;
      if (a.status === 401) {
        sessionEpoch.current++;
        newAttempt.current = null;
        stop();
        setToken(null);
        setActor(null);
        setHistory([]);
        setCursor(null);
        setFeedback("");
        setFeedbackSent(false);
        setOperatorToken("");
        setDraft(null);
        setObservation(null);
        setImage(null);
        setAssessment(null);
        setScreen("login");
        setError("Сессия завершилась. Войдите снова.");
        return;
      }
      setError(
        a instanceof ApiError
          ? `${a.message}${a.requestId ? ` · код обращения ${a.requestId}` : ""}${a.status === 429 ? ` · повторите через ${a.retryAfter ?? "несколько"} секунд` : ""}`
          : ((e as Error)?.message ??
              "Не удалось подключиться. Проверьте сеть и адрес API."),
      );
    },
    [stop],
  );
  const loadCatalog = useCallback(async () => {
    try {
      setCatalog(await api.catalog());
    } catch (e) {
      handleError(e);
    }
  }, [api, handleError]);
  const loadHistory = useCallback(
    async (append = false) => {
      if (!tokenRef.current) return;
      const epoch = sessionEpoch.current;
      try {
        const p = await api.history(append ? (cursor ?? undefined) : undefined);
        if (epoch !== sessionEpoch.current) return;
        setHistory((old) =>
          append
            ? [
                ...old,
                ...p.items.filter((n) => !old.some((o) => o.id === n.id)),
              ]
            : p.items,
        );
        setCursor(p.next_cursor);
      } catch (e) {
        if (epoch === sessionEpoch.current) handleError(e);
      }
    },
    [api, cursor, handleError],
  );
  useEffect(() => {
    void loadCatalog();
    const epoch = sessionEpoch.current;
    if (authMode === "oidc")
      void restoreOidc()
        .then((t) => {
          if (t && epoch === sessionEpoch.current) setToken(t);
        })
        .catch(handleError);
    return stop;
  }, []);
  useEffect(() => {
    if (!token) return;
    const epoch = sessionEpoch.current;
    void api
      .me()
      .then((a) => {
        if (epoch === sessionEpoch.current) {
          setActor(a);
          void loadHistory();
        }
      })
      .catch(handleError);
  }, [token]);
  useEffect(() => {
    const sub = BackHandler.addEventListener("hardwareBackPress", () => {
      if (screen === "home") return false;
      navigate(screen === "preview" ? "capture" : "home");
      return true;
    });
    return () => sub.remove();
  }, [screen, navigate]);
  useEffect(() => {
    const sub = AppState.addEventListener("change", (state) => {
      if (state !== "active") stop();
    });
    return () => sub.remove();
  }, [stop]);
  const login = async () => {
    const epoch = sessionEpoch.current;
    setBusy(true);
    setError("");
    try {
      const t =
        authMode === "development"
          ? operatorToken.trim().replace(/^Bearer\s+/i, "")
          : await signInOidc();
      if (!t || epoch !== sessionEpoch.current) return;
      tokenRef.current = t;
      await api.me();
      if (epoch !== sessionEpoch.current) return;
      sessionEpoch.current++;
      setToken(t);
      setOperatorToken("");
      navigate("home");
    } catch (e) {
      tokenRef.current = null;
      handleError(e);
    } finally {
      setBusy(false);
    }
  };
  const logout = async () => {
    sessionEpoch.current++;
    newAttempt.current = null;
    stop();
    tokenRef.current = null;
    setToken(null);
    setActor(null);
    setHistory([]);
    setCursor(null);
    setDraft(null);
    setObservation(null);
    setAssessment(null);
    setImage(null);
    setFeedback("");
    setOperatorToken("");
    navigate("home");
    await clearSession();
  };
  const start = () => {
    if (!token) {
      navigate("login");
      return;
    }
    setDraft(null);
    newAttempt.current = null;
    setImage(null);
    setAssessment(null);
    setObservation(null);
    setCrop(null);
    setFeedback("");
    setFeedbackSent(false);
    navigate("crops");
  };
  const pick = async (camera: boolean) => {
    const epoch = sessionEpoch.current;
    setError("");
    setBusy(true);
    try {
      if (camera) {
        const p = await ImagePicker.requestCameraPermissionsAsync();
        if (!p.granted) {
          setError(
            "Разрешите камеру в настройках Android или выберите снимок из галереи.",
          );
          return;
        }
      }
      const response = await (camera
        ? ImagePicker.launchCameraAsync({
            mediaTypes: ["images"],
            quality: 0.95,
            exif: false,
          })
        : ImagePicker.launchImageLibraryAsync({
            mediaTypes: ["images"],
            quality: 0.95,
            exif: false,
          }));
      if (response.canceled || epoch !== sessionEpoch.current) return;
      const asset = response.assets[0];
      const resize =
        asset.width > 2048 || asset.height > 2048
          ? [
              {
                resize:
                  asset.width >= asset.height
                    ? { width: 2048 }
                    : { height: 2048 },
              },
            ]
          : [];
      const processed = await ImageManipulator.manipulateAsync(
        asset.uri,
        resize,
        { compress: 0.9, format: ImageManipulator.SaveFormat.JPEG },
      );
      if (epoch !== sessionEpoch.current) return;
      const d: Draft = {
        observationId: Crypto.randomUUID(),
        photoId: Crypto.randomUUID(),
        key: Crypto.randomUUID(),
        cropId: crop!.id,
        capturedAt: new Date().toISOString(),
        notes: "",
        uri: processed.uri,
      };
      setDraft(d);
      setImage({ uri: d.uri });
      navigate("preview");
    } catch (e) {
      handleError(e);
    } finally {
      setBusy(false);
    }
  };
  const watch = async (id: string, controller: AbortController) => {
    const a = await pollAssessment(api, id, controller.signal, setAssessment);
    setAssessment(a);
    setScreen("result");
    void loadHistory();
  };
  const submit = async () => {
    if (!draft || !crop || submitLock.current) return;
    submitLock.current = true;
    stop();
    const controller = new AbortController();
    active.current = controller;
    setBusy(true);
    setError("");
    setScreen("progress");
    try {
      const r = await runSubmission(
        api,
        draft,
        crop.can_assess,
        controller.signal,
        setStage,
      );
      if (r.assessment) {
        setAssessment(r.assessment);
        await watch(r.assessment.id, controller);
      } else {
        setObservation(
          await api.observation(r.observationId, controller.signal),
        );
        setAssessment(null);
        setScreen("result");
        void loadHistory();
      }
    } catch (e) {
      handleError(e);
    } finally {
      submitLock.current = false;
      setBusy(false);
    }
  };
  const resume = async () => {
    if (!assessment) return;
    stop();
    const c = new AbortController();
    active.current = c;
    setBusy(true);
    setError("");
    try {
      await watch(assessment.id, c);
    } catch (e) {
      handleError(e);
    } finally {
      setBusy(false);
    }
  };
  const retryFailed = async () => {
    if (!assessment || submitLock.current) return;
    submitLock.current = true;
    const old = assessment;
    if (newAttempt.current?.source !== old.id)
      newAttempt.current = { source: old.id, key: Crypto.randomUUID() };
    stop();
    const c = new AbortController();
    active.current = c;
    setBusy(true);
    setError("");
    setStage("Создаём новую попытку");
    setScreen("progress");
    try {
      const next = await api.createAssessment(
        {
          observation_id: old.observation_id,
          primary_photo_id: old.primary_photo_id,
        },
        newAttempt.current!.key,
        c.signal,
      );
      newAttempt.current = null;
      setAssessment(next);
      await watch(next.id, c);
    } catch (e) {
      handleError(e);
    } finally {
      submitLock.current = false;
      setBusy(false);
    }
  };
  const openObservation = async (o: Schemas["ObservationRead"]) => {
    newAttempt.current = null;
    navigate("result");
    const c = new AbortController();
    active.current = c;
    setBusy(true);
    setError("");
    setDraft(null);
    setImage(null);
    setObservation(o);
    setAssessment(o.assessments.at(-1) ?? null);
    setFeedbackSent(false);
    setFeedback("");
    try {
      const p = o.photos.find((p) => p.status === "ready");
      if (p) {
        const u = await api.contentUrl(p.id, c.signal);
        if (!c.signal.aborted) setImage(api.privateImage(u.url));
      }
    } catch (e) {
      handleError(e);
    } finally {
      setBusy(false);
    }
  };
  const rows = (items: Schemas["ObservationRead"][]) =>
    items.map((o) => (
      <Pressable
        key={o.id}
        onPress={() => void openObservation(o)}
        accessibilityRole="button"
        style={s.row}
      >
        <Text style={s.label}>
          {catalog?.crops.find((c) => c.id === o.crop_id)?.name_ru ?? o.crop_id}{" "}
          · лист
        </Text>
        <Text style={s.caption}>
          {new Date(o.captured_at).toLocaleDateString("ru-RU")} ·{" "}
          {o.assessments.length
            ? {
                queued: "В очереди",
                running: "Анализируется",
                completed: "Результат готов",
                failed: "Технический сбой",
              }[o.assessments.at(-1)!.status]
            : "Сохранено без анализа"}
        </Text>
        {o.notes && (
          <Text numberOfLines={2} style={s.caption}>
            {o.notes}
          </Text>
        )}
      </Pressable>
    ));
  const result = assessment?.result;
  const copy = result ? outcomeCopy(result.outcome, result.reason_codes) : null;
  const researchModel =
    catalog?.crops.some(
      (c) => c.model_version && !c.model_version.startsWith("dev-synthetic"),
    ) ?? false;
  const primary =
    screen === "home" || screen === "history" || screen === "crops";
  return (
    <SafeAreaView style={s.safe} edges={["top", "bottom"]}>
      <StatusBar barStyle="dark-content" backgroundColor={C.background} />
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <View style={s.top}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="На главную"
            onPress={() => navigate("home")}
            style={{ minHeight: 48, justifyContent: "center" }}
          >
            <Text style={s.brand}>
              {primary ? "AgroVision" : "‹ AgroVision"}
            </Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            onPress={() =>
              token
                ? Alert.alert(
                    "Аккаунт",
                    actor?.display_name ?? "Вы вошли в AgroVision",
                    [
                      { text: "Закрыть" },
                      { text: "Выйти", onPress: () => void logout() },
                    ],
                  )
                : navigate("login")
            }
            style={s.account}
          >
            <Text style={s.caption}>{token ? "Аккаунт" : "Войти"}</Text>
          </Pressable>
        </View>
        <ScrollView
          contentContainerStyle={s.content}
          keyboardShouldPersistTaps="handled"
          refreshControl={
            primary ? (
              <RefreshControl
                refreshing={refreshing}
                onRefresh={() => {
                  setRefreshing(true);
                  Promise.all([loadCatalog(), loadHistory()]).finally(() =>
                    setRefreshing(false),
                  );
                }}
                tintColor={C.brand}
              />
            ) : undefined
          }
        >
          {catalog?.runtime_mode === "development" && (
            <Notice
              warning
              title={
                researchModel
                  ? "Исследовательская модель"
                  : "Демонстрационный режим"
              }
              body={
                researchModel
                  ? "Реальная модель показывает исследовательские гипотезы. Диагностические пороги и полевая работа ещё не проверены."
                  : "Обработчик проверяет работу приложения. Диагноз и оценка вероятности не выполняются."
              }
            />
          )}
          {error !== "" && (
            <View
              accessibilityRole="alert"
              style={[s.notice, { backgroundColor: "#fbe9e5" }]}
            >
              <Text style={[s.body, { color: C.danger }]}>{error}</Text>
              <Button
                label="Закрыть сообщение"
                secondary
                onPress={() => setError("")}
              />
            </View>
          )}
          {screen === "home" && (
            <>
              <View style={s.pill}>
                <Text style={s.caption}>Полевой помощник</Text>
              </View>
              <Heading
                title="Забота о растениях начинается с фото"
                body="Сохраните наблюдение и проверьте видимые признаки на листе."
              />
              <View style={s.hero}>
                <Text style={[s.title, { color: "white" }]}>
                  Что с моим растением?
                </Text>
                <Text style={[s.body, { color: "white" }]}>
                  Выберите культуру. Снимите один лист крупным планом.
                </Text>
              </View>
              <Button label="Новое наблюдение" onPress={start} />
              <Text style={s.title}>Последние наблюдения</Text>
              {history.length ? (
                rows(history.slice(0, 3))
              ) : (
                <Notice
                  title={
                    token ? "Пока нет наблюдений" : "Ваша история в одном месте"
                  }
                  body={
                    token
                      ? "Первое фото появится здесь после сохранения."
                      : "Войдите, чтобы сохранять снимки и возвращаться к результатам."
                  }
                />
              )}
              <Text style={s.caption}>
                Фото помогает оценить внешние признаки. Для подтверждения
                причины повреждения нужен специалист.
              </Text>
              {!catalog && (
                <Button
                  label="Повторить подключение"
                  secondary
                  onPress={() => void loadCatalog()}
                />
              )}
            </>
          )}
          {screen === "login" && (
            <>
              <Heading
                title="Ваши наблюдения — под защитой"
                body="Войдите, чтобы сохранять снимки и видеть только свою историю."
              />
              {authMode === "development" ? (
                <>
                  <Notice
                    warning
                    title="Вход для локальной разработки"
                    body="Введите подписанный токен оператора. Он хранится только в памяти приложения и исчезнет после закрытия."
                  />
                  <TextInput
                    accessibilityLabel="Токен оператора"
                    style={s.input}
                    secureTextEntry
                    autoCapitalize="none"
                    autoCorrect={false}
                    value={operatorToken}
                    onChangeText={setOperatorToken}
                    placeholder="Bearer token"
                  />
                </>
              ) : (
                <Notice
                  title="Безопасный вход"
                  body="Откроется страница вашего провайдера. Пароль не передаётся AgroVision."
                />
              )}
              <Button
                disabled={
                  busy || (authMode === "development" && !operatorToken.trim())
                }
                label={busy ? "Подключаемся…" : "Войти"}
                onPress={() => void login()}
              />
              <Button
                secondary
                label="Вернуться на главную"
                onPress={() => navigate("home")}
              />
            </>
          )}
          {screen === "crops" && (
            <>
              <Heading
                title="Какая это культура?"
                body="Выбор культуры определяет доступные возможности анализа."
              />
              {catalog?.crops.map((c) => (
                <Pressable
                  accessibilityRole="button"
                  key={c.id}
                  style={s.row}
                  onPress={() => {
                    setCrop(c);
                    navigate("capture");
                  }}
                >
                  <Text style={s.label}>{c.name_ru}</Text>
                  <Text style={s.caption}>
                    {c.can_assess
                      ? c.support_status === "development"
                        ? c.model_version?.startsWith("dev-synthetic")
                          ? "Демонстрационная обработка"
                          : "Исследовательская оценка листа"
                        : "Проверка листьев"
                      : "Сохранение фото без анализа"}
                  </Text>
                </Pressable>
              ))}
              {!catalog && (
                <Button
                  secondary
                  label="Загрузить каталог"
                  onPress={() => void loadCatalog()}
                />
              )}
              <Notice
                title="Один лист — один анализ"
                body="Выберите культуру, затем снимите один лист крупным планом. Доступность определяется каталогом сервера."
              />
            </>
          )}
          {screen === "capture" && (
            <>
              <Heading
                title={`${crop?.name_ru ?? "Растение"} · лист`}
                body="Найдите лист с заметными признаками. Снимайте при мягком дневном свете."
              />
              {!crop?.can_assess && (
                <Notice
                  warning
                  title="Анализ пока недоступен"
                  body="Фото и заметку можно сохранить в истории без диагностического вывода."
                />
              )}
              <View style={s.capture}>
                <Text
                  style={[s.heading, { color: C.brand, textAlign: "center" }]}
                >
                  Один лист{"\n"}крупным планом
                </Text>
                <Text style={[s.muted, { textAlign: "center" }]}>
                  Резкость · равномерный свет · весь лист в кадре
                </Text>
              </View>
              <Button
                disabled={busy}
                label={busy ? "Подготавливаем фото…" : "Открыть камеру"}
                onPress={() => void pick(true)}
              />
              <Button
                disabled={busy}
                secondary
                label="Выбрать из галереи"
                onPress={() => void pick(false)}
              />
              <Button
                secondary
                label="Изменить культуру"
                onPress={() => navigate("crops")}
              />
              <Text style={s.caption}>
                Разрешение камеры запрашивается только при съёмке. Из галереи
                передаётся только выбранный снимок.
              </Text>
            </>
          )}
          {screen === "preview" && draft && (
            <>
              <Heading
                title="Всё хорошо видно?"
                body="Проверьте резкость и освещение перед отправкой."
              />
              <Image
                source={{ uri: draft.uri }}
                style={s.photo}
                accessibilityLabel="Основной снимок листа"
              />
              <View style={s.row}>
                <Text style={s.label}>{crop?.name_ru} · лист</Text>
                <Text style={s.caption}>Основное фото для одного анализа</Text>
              </View>
              <TextInput
                accessibilityLabel="Заметка к наблюдению"
                style={[s.input, { minHeight: 100, textAlignVertical: "top" }]}
                multiline
                maxLength={1000}
                value={draft.notes}
                onChangeText={(notes) => setDraft({ ...draft, notes })}
                placeholder="Что вы заметили? Заметка необязательна"
              />
              <Text style={s.caption}>
                {draft.notes.length}/1000 · запись без привязки к участку
              </Text>
              <Button
                label={
                  crop?.can_assess
                    ? "Отправить на анализ"
                    : "Сохранить без анализа"
                }
                onPress={() => void submit()}
              />
              <Button
                secondary
                label="Переснять фото"
                onPress={() => navigate("capture")}
              />
              <Text style={s.caption}>
                Снимок будет загружен на сервер и сохранён в вашей истории. Для
                отправки нужна сеть.
              </Text>
            </>
          )}
          {screen === "progress" && (
            <>
              <Heading
                title={
                  assessment?.status === "running"
                    ? "Рассматриваем снимок"
                    : "Сохраняем наблюдение"
                }
                body="Можно вернуться к истории. Принятая сервером оценка продолжится."
              />
              {image && <Image source={image} style={s.photo} />}
              <View style={s.notice}>
                {busy && <ActivityIndicator size="large" color={C.action} />}
                <Text accessibilityLiveRegion="polite" style={s.title}>
                  {assessment
                    ? {
                        queued: "Оценка принята в очередь",
                        running: "Выполняется обработка",
                        completed: "Готово",
                        failed: "Обработка завершилась с ошибкой",
                      }[assessment.status]
                    : stage}
                </Text>
              </View>
              {!busy && (
                <Button
                  label="Продолжить"
                  onPress={() =>
                    void (newAttempt.current
                      ? retryFailed()
                      : assessment
                        ? resume()
                        : submit())
                  }
                />
              )}
              <Button
                secondary
                label="Открыть историю"
                onPress={() => {
                  navigate("history");
                  void loadHistory();
                }}
              />
              <Text style={s.caption}>
                Уход с экрана прекращает ожидание на устройстве. Уже сохранённые
                записи остаются на сервере.
              </Text>
            </>
          )}
          {screen === "result" && (
            <>
              {assessment?.status === "failed" ? (
                <>
                  <Heading
                    title="Не удалось обработать снимок"
                    body={
                      assessment.error?.message ??
                      "Техническая ошибка сервиса. Фото сохранено в истории."
                    }
                  />
                  <Notice
                    warning
                    title="Это технический сбой"
                    body="Ошибка обработки ничего не говорит о состоянии растения."
                  />
                  {assessment.error?.retryable && (
                    <Button
                      label="Создать новую попытку"
                      onPress={() => void retryFailed()}
                    />
                  )}
                </>
              ) : assessment?.status === "queued" ||
                assessment?.status === "running" ? (
                <>
                  <Heading title="Оценка ещё выполняется" />
                  <Button
                    label="Продолжить ожидание"
                    onPress={() => {
                      setScreen("progress");
                      void resume();
                    }}
                  />
                </>
              ) : copy && result ? (
                <>
                  <View style={[s.pill, { backgroundColor: C.warning }]}>
                    <Text style={s.caption}>
                      {result.reason_codes.includes(
                        "research_model_unvalidated",
                      )
                        ? "Исследовательский результат"
                        : "Предварительный вывод"}
                    </Text>
                  </View>
                  <Heading
                    title={
                      result.outcome === "predicted" && result.prediction
                        ? conditionLabel(result.prediction.condition_id)
                        : copy.title
                    }
                  />
                  {image && (
                    <Image
                      source={image}
                      style={s.photo}
                      accessibilityLabel="Сохранённый основной снимок"
                    />
                  )}
                  <Notice warning title="Что сделать дальше" body={copy.body} />
                  {result.reason_codes.map((code) => (
                    <Text key={code} style={s.body}>
                      •{" "}
                      {reasons[code] ??
                        "Модель не смогла подтвердить достаточность данных."}
                    </Text>
                  ))}
                  {result.candidates.length > 0 && (
                    <>
                      <Text style={s.label}>
                        {result.outcome === "predicted"
                          ? "Другие гипотезы модели"
                          : "Исследовательские гипотезы · не диагноз"}
                      </Text>
                      {result.candidates.map((c) => (
                        <Text key={c.class_id} style={s.muted}>
                          {conditionLabel(c.condition_id)}
                        </Text>
                      ))}
                    </>
                  )}
                  <Text style={s.caption}>
                    Качество снимка:{" "}
                    {
                      {
                        passed: "проверки пройдены",
                        warning: "есть замечания",
                        unusable: "требуется пересъёмка",
                        not_assessed: "не оценивалось",
                      }[result.quality.status]
                    }
                    . Проверка качества не гарантирует правильность вывода.
                  </Text>
                  <Text selectable style={s.caption}>
                    Модель: {assessment?.model.version} · политика{" "}
                    {assessment?.model.decision_policy_version}
                  </Text>
                  <Text style={s.label}>Был ли результат полезен?</Text>
                  {feedbackSent ? (
                    <Notice
                      title="Спасибо, отзыв сохранён"
                      body="Отзыв помогает оценить систему и не меняет результат модели."
                    />
                  ) : (
                    <>
                      <TextInput
                        accessibilityLabel="Комментарий к результату"
                        style={s.input}
                        value={feedback}
                        onChangeText={setFeedback}
                        maxLength={1000}
                        placeholder="Комментарий об ошибке или результате"
                      />
                      <Button
                        secondary
                        disabled={busy}
                        label="Результат полезен"
                        onPress={() => {
                          if (!assessment) return;
                          setBusy(true);
                          void api
                            .feedback(assessment.id, {
                              helpful: true,
                              suspected_error: false,
                              note: feedback || null,
                            })
                            .then(() => setFeedbackSent(true))
                            .catch(handleError)
                            .finally(() => setBusy(false));
                        }}
                      />
                      <Button
                        secondary
                        disabled={busy}
                        label="Сообщить о возможной ошибке"
                        onPress={() => {
                          if (!assessment) return;
                          setBusy(true);
                          void api
                            .feedback(assessment.id, {
                              helpful: null,
                              suspected_error: true,
                              note: feedback || null,
                            })
                            .then(() => setFeedbackSent(true))
                            .catch(handleError)
                            .finally(() => setBusy(false));
                        }}
                      />
                    </>
                  )}
                </>
              ) : (
                <>
                  <Heading
                    title="Наблюдение сохранено"
                    body="Фото и заметка находятся в вашей истории. Анализ для этой культуры не выполнялся."
                  />
                  {image && <Image source={image} style={s.photo} />}
                </>
              )}
              <Button label="Новое наблюдение" onPress={start} />
              <Button
                secondary
                label="К истории"
                onPress={() => {
                  navigate("history");
                  void loadHistory();
                }}
              />
              {(observation || assessment) && (
                <Button
                  secondary
                  label="Удалить наблюдение"
                  onPress={() =>
                    Alert.alert(
                      "Удалить наблюдение?",
                      "Фото и результаты станут недоступны.",
                      [
                        { text: "Отмена" },
                        {
                          text: "Удалить",
                          style: "destructive",
                          onPress: () => {
                            const id =
                              observation?.id ?? assessment!.observation_id;
                            setBusy(true);
                            void api
                              .deleteObservation(id)
                              .then(() => {
                                setImage(null);
                                setObservation(null);
                                setAssessment(null);
                                navigate("history");
                                void loadHistory();
                              })
                              .catch(handleError)
                              .finally(() => setBusy(false));
                          },
                        },
                      ],
                    )
                  }
                />
              )}
            </>
          )}
          {screen === "history" && (
            <>
              <Heading
                title="История наблюдений"
                body="Ваши снимки и предварительные результаты."
              />
              {!token ? (
                <Button label="Войти" onPress={() => navigate("login")} />
              ) : history.length ? (
                rows(history)
              ) : (
                <Notice
                  title="Пока нет наблюдений"
                  body="Создайте первое наблюдение — оно появится здесь после сохранения."
                />
              )}
              {cursor && (
                <Button
                  secondary
                  label="Показать ещё"
                  onPress={() => void loadHistory(true)}
                />
              )}
              <Button label="Новое наблюдение" onPress={start} />
            </>
          )}
        </ScrollView>
        {primary && (
          <BottomNavigation.Bar
            safeAreaInsets={{ bottom: 0 }}
            navigationState={{
              index: screen === "home" ? 0 : screen === "crops" ? 1 : 2,
              routes: [
                { key: "home", title: "Главная", focusedIcon: "home-outline" },
                {
                  key: "crops",
                  title: "Снять фото",
                  focusedIcon: "camera-outline",
                },
                { key: "history", title: "История", focusedIcon: "history" },
              ],
            }}
            onTabPress={({ route }) =>
              route.key === "crops"
                ? start()
                : (navigate(route.key as Screen),
                  route.key === "history" && void loadHistory())
            }
            style={{ backgroundColor: C.surface }}
            activeColor={C.brand}
            inactiveColor={C.muted}
          />
        )}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
export default function App() {
  return (
    <SafeAreaProvider>
      <PaperProvider theme={theme}>
        <AppContent />
      </PaperProvider>
    </SafeAreaProvider>
  );
}
const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.background },
  top: {
    minHeight: 56,
    paddingHorizontal: 20,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  brand: { fontSize: 14, fontWeight: "600", color: C.brand },
  account: { padding: 12, minHeight: 48, justifyContent: "center" },
  content: {
    padding: 20,
    paddingTop: 12,
    gap: 12,
    width: "100%",
    maxWidth: 600,
    alignSelf: "center",
    paddingBottom: 32,
  },
  heading: { fontSize: 28, lineHeight: 34, fontWeight: "700", color: C.text },
  title: { fontSize: 20, lineHeight: 26, fontWeight: "700", color: C.text },
  label: { fontSize: 14, lineHeight: 20, fontWeight: "600", color: C.brand },
  body: { fontSize: 15, lineHeight: 22, color: C.text },
  muted: { fontSize: 15, lineHeight: 22, color: C.muted },
  caption: { fontSize: 12, lineHeight: 17, color: C.muted },
  pill: {
    alignSelf: "flex-start",
    borderRadius: 100,
    backgroundColor: C.tint,
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  hero: { backgroundColor: C.brand, borderRadius: 16, padding: 20, gap: 12 },
  notice: { backgroundColor: C.tint, borderRadius: 16, padding: 16, gap: 12 },
  row: {
    minHeight: 82,
    backgroundColor: C.surface,
    borderRadius: 16,
    padding: 16,
    gap: 4,
    justifyContent: "center",
  },
  button: {
    backgroundColor: C.action,
    borderRadius: 16,
    paddingHorizontal: 20,
    paddingVertical: 16,
    minHeight: 56,
    justifyContent: "center",
    alignItems: "center",
  },
  secondary: {
    backgroundColor: C.surface,
    borderWidth: 1,
    borderColor: C.border,
  },
  buttonText: {
    fontSize: 16,
    fontWeight: "600",
    color: C.surface,
    textAlign: "center",
  },
  input: {
    backgroundColor: C.surface,
    borderWidth: 1,
    borderColor: C.border,
    borderRadius: 16,
    padding: 16,
    fontSize: 15,
    color: C.text,
    minHeight: 56,
  },
  photo: {
    width: "100%",
    height: 240,
    resizeMode: "contain",
    backgroundColor: C.tint,
    borderRadius: 20,
  },
  capture: {
    borderWidth: 2,
    borderColor: C.border,
    borderStyle: "dashed",
    borderRadius: 24,
    padding: 32,
    minHeight: 250,
    justifyContent: "center",
    gap: 20,
  },
});
