from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "client" / "src"
APP_TSX = ROOT / "App.tsx"
LAYOUT_TSX = ROOT / "components" / "Layout.tsx"
CATEGORIES_TSX = ROOT / "pages" / "Categories.tsx"
DASHBOARD_TSX = ROOT / "pages" / "Dashboard.tsx"
I18N_TS = ROOT / "hooks" / "use-i18n.ts"
FASTAPI_AUTHORITY_TEST = Path(__file__).resolve().parent / "test_react_fastapi_authority.py"


def test_categories_page_route_nav_and_permission_contracts():
    app_src = APP_TSX.read_text(encoding="utf-8")
    layout_src = LAYOUT_TSX.read_text(encoding="utf-8")
    authority_src = FASTAPI_AUTHORITY_TEST.read_text(encoding="utf-8")

    assert 'import Categories from "@/pages/Categories"' in app_src
    assert 'path="/categories"' in app_src
    assert 'permission="files.read"' in app_src
    assert '<Categories />' in app_src

    assert 'path: "/categories"' in layout_src
    assert 'labelKey: "nav.categories"' in layout_src
    assert 'permission: "files.read"' in layout_src
    assert "Tags," in layout_src

    assert 'ROOT / "pages" / "Categories.tsx"' in authority_src


def test_categories_page_uses_fastapi_categories_and_database_filter_links():
    src = CATEGORIES_TSX.read_text(encoding="utf-8")

    assert 'apiGet<CategoriesResponse>("/api/categories?mode=used")' in src
    assert "normalizeCategories(result.categories)" in src
    assert "categoryDisplayName(category, lang)" in src
    assert "function databaseCategoryPath(category: string)" in src
    assert "new URLSearchParams({ category })" in src
    assert "`/database?${params.toString()}`" in src
    assert 'data-testid="categories-grid"' in src
    assert 'data-testid="input-category-search"' in src
    assert 'aria-label={t("categories.search_placeholder")}' in src


def test_dashboard_links_to_standalone_categories_entry():
    src = DASHBOARD_TSX.read_text(encoding="utf-8")

    assert 'href: "/categories"' in src
    assert '<Link href="/categories">' in src
    assert "databaseCategoryPath(category.name)" in src


def test_categories_i18n_has_en_and_zh_labels():
    src = I18N_TS.read_text(encoding="utf-8")

    expected_keys = [
        "nav.categories",
        "categories.title",
        "categories.subtitle",
        "categories.search_placeholder",
        "categories.no_categories",
        "categories.open",
        "categories.load_error",
    ]
    for key in expected_keys:
        assert src.count(f'"{key}"') == 2

    assert "Browse all document topics" in src
    assert "浏览所有文档主题" in src
