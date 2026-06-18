from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "client" / "src"
APP_TSX = ROOT / "App.tsx"
LOGIN_TSX = ROOT / "pages" / "Login.tsx"
REGISTER_TSX = ROOT / "pages" / "Register.tsx"
PROFILE_TSX = ROOT / "pages" / "Profile.tsx"
LAYOUT_TSX = ROOT / "components" / "Layout.tsx"
AUTH_CONTEXT_TSX = ROOT / "context" / "AuthContext.tsx"
API_TS = ROOT / "lib" / "api.ts"
AUTH_ERRORS_TS = ROOT / "lib" / "auth-errors.ts"
I18N_TS = ROOT / "hooks" / "use-i18n.ts"


def test_auth_react_shell_restores_native_auth_routes_and_contracts():
    app_src = APP_TSX.read_text(encoding="utf-8")
    login_src = LOGIN_TSX.read_text(encoding="utf-8")
    register_src = REGISTER_TSX.read_text(encoding="utf-8")
    profile_src = PROFILE_TSX.read_text(encoding="utf-8")
    layout_src = LAYOUT_TSX.read_text(encoding="utf-8")
    auth_ctx_src = AUTH_CONTEXT_TSX.read_text(encoding="utf-8")
    api_src = API_TS.read_text(encoding="utf-8")
    auth_errors_src = AUTH_ERRORS_TS.read_text(encoding="utf-8")
    i18n_src = I18N_TS.read_text(encoding="utf-8")

    assert 'path="/login" component={Login}' in app_src
    assert 'path="/register" component={Register}' in app_src
    assert 'path="/profile"' in app_src
    assert 'path="/users"' in app_src
    assert 'function RequirePermission' in app_src
    assert 'permission="tasks.view"' in app_src
    assert 'permission="config.write"' in app_src
    assert 'permission="users.manage"' in app_src
    assert 'navigate("/login")' in app_src

    assert 'apiPost("/api/auth/login"' in login_src
    assert 'setStoredAuthToken(token.trim(), false)' in login_src
    assert 'setStoredAuthToken("", true)' in login_src
    assert 't("login.title")' in login_src
    assert 't("auth.back_home")' in login_src
    assert 'href="/"' in login_src
    assert 'apiPost("/api/auth/register"' in register_src
    assert 'formatAuthSubmitError' in login_src
    assert 'formatAuthSubmitError' in register_src
    assert 'export function formatAuthSubmitError' in auth_errors_src
    assert 'err.status === 429' in auth_errors_src
    assert 'auth.error.rate_limited' in auth_errors_src
    assert 'auth.error.system_unavailable' in auth_errors_src
    assert '"auth.error.rate_limited": "尝试次数过多，请稍等一分钟再试。"' in i18n_src
    assert '"auth.error.system_unavailable": "服务暂时不可用，请稍后再试。"' in i18n_src
    assert 't("register.title")' in register_src
    assert 't("auth.back_home")' in register_src
    assert 'href="/"' in register_src
    assert 'href="/login"' in profile_src
    assert 'button-logout' in layout_src
    assert 'permission: "tasks.view"' in layout_src
    assert 'permission: "config.write"' in layout_src
    assert 'permissions.includes("users.manage")' in layout_src
    assert 'i18n.t("nav.users")' in layout_src
    assert 'i18n.t("auth.signIn")' in layout_src
    assert 'data-testid="button-login"' in layout_src
    login_button_classes = layout_src.split('data-testid="button-login"', 1)[0].rsplit('className="', 1)[1]
    assert not login_button_classes.startswith("hidden ")
    assert 'i18n.t("auth.register")' in layout_src
    assert 'apiGet<AuthMeResponse>("/api/auth/me")' in auth_ctx_src
    assert 'apiPost("/api/auth/logout")' in auth_ctx_src
    assert 'setStoredAuthToken("", true)' in auth_ctx_src
    assert 'credentials: options?.credentials ?? "include"' in api_src
    assert 'readCookie("csrf_token")' in api_src
    assert 'headers["X-CSRF-Token"] = csrfToken' in api_src
    assert '"auth.signIn"' in i18n_src
    assert '"auth.register"' in i18n_src
    assert '"auth.back_home"' in i18n_src
    assert '"login.title"' in i18n_src
    assert '"register.title"' in i18n_src
    assert '"auth.back_home": "返回主页"' in i18n_src
    assert '"login.title": "登录"' in i18n_src
    assert '"register.title": "创建账号"' in i18n_src
