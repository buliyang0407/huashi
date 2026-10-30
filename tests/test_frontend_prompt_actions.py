from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FrontendPromptActionsTest(unittest.TestCase):
    def test_prompt_cards_expose_direct_copy_action(self):
        app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("data-copy-prompt", app_js)
        self.assertIn("copyPrompt", app_js)

    def test_portrait_results_can_be_saved_and_imported_to_apps(self):
        app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("data-save-portrait-prompt", app_js)
        self.assertIn("savePortraitPromptPreset", app_js)
        self.assertIn("data-import-portrait-prompt", app_js)
        self.assertIn("importPortraitPromptToApp", app_js)

    def test_portrait_material_draft_workspace_stays_out_of_formal_ui(self):
        app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        index_html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

        self.assertNotIn("/api/portrait/material-drafts", app_js)
        self.assertNotIn("generatePortraitMaterialDrafts", app_js)
        self.assertNotIn("portraitDraftCategoryInput", index_html)
        self.assertNotIn("素材扩展", index_html)

    def test_portrait_flow_uses_new_cache_and_detail_groups(self):
        app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("huashiPortraitCatalog:v5", app_js)
        self.assertIn('subgroup("hair", "发饰"', app_js)
        self.assertIn('subgroup("glass", "玻璃水汽"', app_js)
        self.assertIn('subgroup("bright", "元气自然"', app_js)

    def test_portrait_workbench_can_import_prompt_analysis_into_slots(self):
        app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        index_html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

        self.assertIn("portraitImportPromptInput", index_html)
        self.assertIn("analyzePortraitImportPrompt", app_js)
        self.assertIn('/api/prompt-agent/analyze', app_js)
        self.assertIn("mapPortraitImportItems", app_js)
        self.assertIn("applyPortraitImportAnalysis", app_js)
        self.assertIn("portraitImportSlotDrafts", app_js)
        self.assertIn("focusPortraitImportDraft", app_js)

    def test_portrait_workbench_uses_text_first_slot_editor(self):
        app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        index_html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        styles_css = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("portraitSlotEditor", index_html)
        self.assertIn("renderPortraitSlotEditor", app_js)
        self.assertIn("portraitStepAutoAdvance", app_js)
        self.assertIn("portraitPreviewId", app_js)
        self.assertIn("data-portrait-preview", app_js)
        # The slot editor remains text driven; the material library now intentionally
        # shows existing images. Lazy loading and selection are checked in browser acceptance.
        self.assertIn(".portrait-slot-row", styles_css)

    def test_prompt_capable_apps_include_text_prompt_like_fields(self):
        app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("输入文本", app_js)
        self.assertIn("caption", app_js)

    def test_gallery_and_picker_expose_face_library(self):
        app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("__faces__", app_js)
        self.assertIn("/api/faces", app_js)
        self.assertIn("renderFaceGallery", app_js)
        self.assertIn("renderArtworkFacePicker", app_js)

    def test_render_only_draws_the_active_screen(self):
        app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        render_block = app_js.split("function render() {", 1)[1].split("\n}", 1)[0]

        self.assertIn("renderActiveScreen(activeScreen)", render_block)
        self.assertIn("function renderActiveScreen(activeScreen)", app_js)
        self.assertNotIn("renderResult();", render_block)
        self.assertNotIn("renderHistory();", render_block)
        self.assertNotIn("renderGallery();", render_block)

    def test_preview_images_prefer_thumbnail_urls(self):
        app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("function previewUrl", app_js)
        self.assertIn("item.thumb_url", app_js)
        self.assertIn("app.icon_thumb_url || app.icon_url || app.cover_thumb_url || app.cover_url", app_js)
        self.assertIn("task.input_thumb_url || task.input_url", app_js)

    def test_history_uses_shared_bounded_page_and_lazy_rows(self):
        app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("const HISTORY_PAGE_SIZE = 20", app_js)
        self.assertIn("historyPageSize: HISTORY_PAGE_SIZE", app_js)
        self.assertIn("tasks.slice(w.start,w.end).map(recordRow)", app_js)
        self.assertIn('$("historyPagination")', app_js)
        self.assertIn("state.historyPage = 0", app_js)

    def test_task_list_uses_summaries_and_lazy_loads_detail(self):
        app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn('"/api/tasks?summary=1&limit=120"', app_js)
        self.assertIn("async function loadTaskDetail(taskId)", app_js)
        self.assertIn("task.is_summary", app_js)
        self.assertIn("loadTaskDetail(task.id)", app_js)
        self.assertIn("state.tasks = state.tasks.map((item) => item.id === task.id ? task : item)", app_js)


if __name__ == "__main__":
    unittest.main()
