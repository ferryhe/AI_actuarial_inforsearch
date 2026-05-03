from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "client" / "src"
APP_TSX = ROOT / "App.tsx"
LOGIN_TSX = ROOT / "pages" / "Login.tsx"
REGISTER_TSX = ROOT / "pages" / "Register.tsx"
PROFILE_TSX = ROOT / "pages" / "Profile.tsx"
LAYOUT_TSX = ROOT / "components" / "Layout.tsx"
AUTH_CONTEXT_TSX = ROOT / "context" / "AuthContext.tsx"
API_TS = ROOT / "lib" / "api.ts"
I18N_TS = ROOT / "hooks" / "use-i18n.ts"


def test_auth_react_shell_restores_native_auth_routes_and_contracts():
    app_src = APP_TSX.read_text(encoding="utf-8")
    login_src = LOGIN_TSX.read_text(encoding="utf-8")
    register_src = REGISTER_TSX.read_text(encoding="utf-8")
    profile_src = PROFILE_TSX.read_text(encoding="utf-8")
    layout_src = LAYOUT_TSX.read_text(encoding="utf-8")
    auth_ctx_src = AUTH_CONTEXT_TSX.read_text(encoding="utf-8")
    api_src = API_TS.read_text(encoding="utf-8")
    i18n_src = I18N_TS.read_text(encoding="utf-8")

    assert 'path="/login" component={Login}' in app_src
    assert 'path="/register" component={Register}' in app_src
    assert 'path="/profile"' in app_src
    assert 'path="/users"' in app_src
    assert 'navigate("/login")' in app_src

    assert 'apiPost("/api/auth/login"' in login_src
    assert 'setStoredAuthToken(token.trim(), false)' in login_src
    assert 'setStoredAuthToken("", true)' in login_src
    assert 'apiPost("/api/auth/register"' in register_src
    assert 'href="/login"' in profile_src
    assert 'button-logout' in layout_src
    assert 'i18n.t("nav.users")' in layout_src
    assert 'i18n.t("auth.signIn")' in layout_src
    assert 'i18n.t("auth.register")' in layout_src
    assert 'apiGet<AuthMeResponse>("/api/auth/me")' in auth_ctx_src
    assert 'apiPost("/api/auth/logout")' in auth_ctx_src
    assert 'setStoredAuthToken("", true)' in auth_ctx_src
    assert 'credentials: options?.credentials ?? "include"' in api_src
    assert 'readCookie("csrf_token")' in api_src
    assert 'headers["X-CSRF-Token"] = csrfToken' in api_src
    assert '"auth.signIn"' in i18n_src
    assert '"auth.register"' in i18n_src
