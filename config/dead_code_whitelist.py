"""Reviewed symbol references for framework-discovered Python entry points."""

from ai_actuarial.api.routers.agentic_rag import (
    api_agentic_rag_chat,
    api_search_agentic_calculation_terms,
    api_search_agentic_formula_cards,
    api_search_agentic_sections,
    api_search_agentic_summaries,
    api_search_agentic_tables,
    api_search_agentic_titles,
    api_trace_agentic_relations,
)

api_search_agentic_summaries  # reason: FastAPI registers this decorated route.
api_search_agentic_titles  # reason: FastAPI registers this decorated route.
api_search_agentic_sections  # reason: FastAPI registers this decorated route.
api_search_agentic_formula_cards  # reason: FastAPI registers this decorated route.
api_search_agentic_tables  # reason: FastAPI registers this decorated route.
api_search_agentic_calculation_terms  # reason: FastAPI registers this decorated route.
api_trace_agentic_relations  # reason: FastAPI registers this decorated route.
api_agentic_rag_chat  # reason: FastAPI registers this decorated route.

from ai_actuarial.api.routers.auth import (
    api_auth_login,
    api_auth_logout,
    api_auth_me,
    api_auth_register,
    api_create_auth_token,
    api_disable_user,
    api_enable_user,
    api_list_auth_tokens,
    api_list_users,
    api_reset_user_quota,
    api_revoke_auth_token,
    api_set_user_role,
    api_update_profile,
    api_user_activity,
    api_user_me,
)

api_auth_me  # reason: FastAPI registers this decorated route.
api_auth_register  # reason: FastAPI registers this decorated route.
api_auth_login  # reason: FastAPI registers this decorated route.
api_auth_logout  # reason: FastAPI registers this decorated route.
api_list_auth_tokens  # reason: FastAPI registers this decorated route.
api_create_auth_token  # reason: FastAPI registers this decorated route.
api_revoke_auth_token  # reason: FastAPI registers this decorated route.
api_user_me  # reason: FastAPI registers this decorated route.
api_update_profile  # reason: FastAPI registers this decorated route.
api_list_users  # reason: FastAPI registers this decorated route.
api_set_user_role  # reason: FastAPI registers this decorated route.
api_enable_user  # reason: FastAPI registers this decorated route.
api_disable_user  # reason: FastAPI registers this decorated route.
api_reset_user_quota  # reason: FastAPI registers this decorated route.
api_user_activity  # reason: FastAPI registers this decorated route.

from ai_actuarial.api.routers.chat import (
    api_chat_query,
    api_create_conversation,
    api_delete_conversation,
    api_get_conversation,
    api_list_available_documents,
    api_list_chat_knowledge_bases,
    api_list_conversations,
)

api_list_conversations  # reason: FastAPI registers this decorated route.
api_create_conversation  # reason: FastAPI registers this decorated route.
api_get_conversation  # reason: FastAPI registers this decorated route.
api_delete_conversation  # reason: FastAPI registers this decorated route.
api_list_chat_knowledge_bases  # reason: FastAPI registers this decorated route.
api_list_available_documents  # reason: FastAPI registers this decorated route.
api_chat_query  # reason: FastAPI registers this decorated route.

from ai_actuarial.api.routers.files_write import (
    api_download,
    api_export,
    api_file_chunk_sets,
    api_file_chunk_sets_generate,
    api_files_delete,
    api_files_import_batches,
    api_files_update,
    api_files_update_markdown,
    api_rag_files_preview,
)

api_files_import_batches  # reason: FastAPI registers this decorated route.
api_files_update  # reason: FastAPI registers this decorated route.
api_files_delete  # reason: FastAPI registers this decorated route.
api_files_update_markdown  # reason: FastAPI registers this decorated route.
api_download  # reason: FastAPI registers this decorated route.
api_export  # reason: FastAPI registers this decorated route.
api_rag_files_preview  # reason: FastAPI registers this decorated route.
api_file_chunk_sets  # reason: FastAPI registers this decorated route.
api_file_chunk_sets_generate  # reason: FastAPI registers this decorated route.

from ai_actuarial.api.routers.meta import (
    api_health,
    health_detailed,
)

api_health  # reason: FastAPI registers this decorated route.
health_detailed  # reason: FastAPI registers this decorated route.

from ai_actuarial.api.routers.metrics import (
    get_metrics,
)

get_metrics  # reason: FastAPI registers this decorated route.

from ai_actuarial.api.routers.migration import (
    api_migration_inventory,
    api_migration_status,
)

api_migration_status  # reason: FastAPI registers this decorated route.
api_migration_inventory  # reason: FastAPI registers this decorated route.

from ai_actuarial.api.routers.ops_read import (
    api_config_ai_models,
    api_config_ai_routing,
    api_config_backend_settings,
    api_config_categories,
    api_config_llm_providers,
    api_config_markdown_conversion,
    api_config_model_catalog,
    api_config_provider_credentials,
    api_config_providers,
    api_config_search_engines,
    api_config_sites,
    api_embedding_coverage,
    api_logs_global,
    api_pipeline_baton_config,
    api_pipeline_baton_status,
    api_schedule_status,
    api_scheduled_tasks,
    api_search,
    api_task_log,
    api_tasks_active,
    api_tasks_history,
)

api_config_sites  # reason: FastAPI registers this decorated route.
api_schedule_status  # reason: FastAPI registers this decorated route.
api_scheduled_tasks  # reason: FastAPI registers this decorated route.
api_pipeline_baton_status  # reason: FastAPI registers this decorated route.
api_pipeline_baton_config  # reason: FastAPI registers this decorated route.
api_tasks_active  # reason: FastAPI registers this decorated route.
api_embedding_coverage  # reason: FastAPI registers this decorated route.
api_tasks_history  # reason: FastAPI registers this decorated route.
api_task_log  # reason: FastAPI registers this decorated route.
api_logs_global  # reason: FastAPI registers this decorated route.
api_config_backend_settings  # reason: FastAPI registers this decorated route.
api_config_markdown_conversion  # reason: FastAPI registers this decorated route.
api_config_llm_providers  # reason: FastAPI registers this decorated route.
api_config_providers  # reason: FastAPI registers this decorated route.
api_config_provider_credentials  # reason: FastAPI registers this decorated route.
api_config_model_catalog  # reason: FastAPI registers this decorated route.
api_config_ai_routing  # reason: FastAPI registers this decorated route.
api_config_ai_models  # reason: FastAPI registers this decorated route.
api_config_search_engines  # reason: FastAPI registers this decorated route.
api_config_categories  # reason: FastAPI registers this decorated route.
api_search  # reason: FastAPI registers this decorated route.

from ai_actuarial.api.routers.ops_write import (
    api_catalog_stats,
    api_chunk_generation_stats,
    api_collections_run,
    api_config_ai_models_update,
    api_config_ai_routing_update,
    api_config_backend_settings_update,
    api_config_backups,
    api_config_backups_create,
    api_config_backups_delete,
    api_config_backups_restore,
    api_config_categories_update,
    api_config_markdown_conversion_update,
    api_config_provider_credentials_delete,
    api_config_provider_credentials_import_env,
    api_config_provider_credentials_reencrypt,
    api_config_provider_credentials_upsert,
    api_config_sites_add,
    api_config_sites_delete,
    api_config_sites_export,
    api_config_sites_import,
    api_config_sites_sample,
    api_config_sites_update,
    api_markdown_conversion_stats,
    api_pipeline_baton_configure,
    api_pipeline_baton_start,
    api_pipeline_baton_tick,
    api_schedule_reinit,
    api_scheduled_tasks_add,
    api_scheduled_tasks_delete,
    api_scheduled_tasks_update,
    api_tasks_stop,
    api_utils_browse_folder,
    api_web_listening_rules_draft,
    api_web_listening_rules_explore,
    api_web_listening_rules_materialize,
    api_web_listening_rules_validate,
)

api_web_listening_rules_explore  # reason: FastAPI registers this decorated route.
api_web_listening_rules_draft  # reason: FastAPI registers this decorated route.
api_web_listening_rules_validate  # reason: FastAPI registers this decorated route.
api_web_listening_rules_materialize  # reason: FastAPI registers this decorated route.
api_config_sites_add  # reason: FastAPI registers this decorated route.
api_config_sites_update  # reason: FastAPI registers this decorated route.
api_config_sites_delete  # reason: FastAPI registers this decorated route.
api_config_sites_import  # reason: FastAPI registers this decorated route.
api_config_sites_export  # reason: FastAPI registers this decorated route.
api_config_sites_sample  # reason: FastAPI registers this decorated route.
api_config_backups  # reason: FastAPI registers this decorated route.
api_config_backups_create  # reason: FastAPI registers this decorated route.
api_config_backups_restore  # reason: FastAPI registers this decorated route.
api_config_backups_delete  # reason: FastAPI registers this decorated route.
api_config_backend_settings_update  # reason: FastAPI registers this decorated route.
api_config_categories_update  # reason: FastAPI registers this decorated route.
api_config_markdown_conversion_update  # reason: FastAPI registers this decorated route.
api_config_ai_models_update  # reason: FastAPI registers this decorated route.
api_config_provider_credentials_upsert  # reason: FastAPI registers this decorated route.
api_config_provider_credentials_import_env  # reason: FastAPI registers this decorated route.
api_config_provider_credentials_reencrypt  # reason: FastAPI registers this decorated route.
api_config_provider_credentials_delete  # reason: FastAPI registers this decorated route.
api_config_ai_routing_update  # reason: FastAPI registers this decorated route.
api_scheduled_tasks_add  # reason: FastAPI registers this decorated route.
api_scheduled_tasks_update  # reason: FastAPI registers this decorated route.
api_scheduled_tasks_delete  # reason: FastAPI registers this decorated route.
api_schedule_reinit  # reason: FastAPI registers this decorated route.
api_pipeline_baton_start  # reason: FastAPI registers this decorated route.
api_pipeline_baton_tick  # reason: FastAPI registers this decorated route.
api_pipeline_baton_configure  # reason: FastAPI registers this decorated route.
api_tasks_stop  # reason: FastAPI registers this decorated route.
api_collections_run  # reason: FastAPI registers this decorated route.
api_utils_browse_folder  # reason: FastAPI registers this decorated route.
api_catalog_stats  # reason: FastAPI registers this decorated route.
api_markdown_conversion_stats  # reason: FastAPI registers this decorated route.
api_chunk_generation_stats  # reason: FastAPI registers this decorated route.

from ai_actuarial.api.routers.rag_admin import (
    api_add_knowledge_base_files,
    api_bind_chunk_sets,
    api_build_agentic_ready_manifest,
    api_categories_mapping,
    api_category_stats,
    api_chunk_profiles,
    api_chunk_sets_cleanup,
    api_create_chunk_profile,
    api_create_index_task,
    api_create_knowledge_base,
    api_delete_chunk_profile,
    api_delete_knowledge_base,
    api_get_agentic_ready_manifest,
    api_get_kb_bindings,
    api_get_kb_categories,
    api_get_knowledge_base,
    api_get_knowledge_base_stats,
    api_list_knowledge_base_files,
    api_list_knowledge_bases,
    api_pending_files,
    api_remove_knowledge_base_file,
    api_selectable_files,
    api_set_kb_categories,
    api_unmapped_categories,
    api_update_chunk_profile,
    api_update_knowledge_base,
)

api_chunk_profiles  # reason: FastAPI registers this decorated route.
api_create_chunk_profile  # reason: FastAPI registers this decorated route.
api_update_chunk_profile  # reason: FastAPI registers this decorated route.
api_delete_chunk_profile  # reason: FastAPI registers this decorated route.
api_chunk_sets_cleanup  # reason: FastAPI registers this decorated route.
api_list_knowledge_bases  # reason: FastAPI registers this decorated route.
api_create_knowledge_base  # reason: FastAPI registers this decorated route.
api_get_knowledge_base  # reason: FastAPI registers this decorated route.
api_update_knowledge_base  # reason: FastAPI registers this decorated route.
api_delete_knowledge_base  # reason: FastAPI registers this decorated route.
api_get_knowledge_base_stats  # reason: FastAPI registers this decorated route.
api_get_agentic_ready_manifest  # reason: FastAPI registers this decorated route.
api_build_agentic_ready_manifest  # reason: FastAPI registers this decorated route.
api_list_knowledge_base_files  # reason: FastAPI registers this decorated route.
api_add_knowledge_base_files  # reason: FastAPI registers this decorated route.
api_remove_knowledge_base_file  # reason: FastAPI registers this decorated route.
api_unmapped_categories  # reason: FastAPI registers this decorated route.
api_categories_mapping  # reason: FastAPI registers this decorated route.
api_category_stats  # reason: FastAPI registers this decorated route.
api_selectable_files  # reason: FastAPI registers this decorated route.
api_get_kb_categories  # reason: FastAPI registers this decorated route.
api_set_kb_categories  # reason: FastAPI registers this decorated route.
api_pending_files  # reason: FastAPI registers this decorated route.
api_bind_chunk_sets  # reason: FastAPI registers this decorated route.
api_get_kb_bindings  # reason: FastAPI registers this decorated route.
api_create_index_task  # reason: FastAPI registers this decorated route.

from ai_actuarial.api.routers.read import (
    api_categories,
    api_file_detail,
    api_file_markdown,
    api_files,
    api_sources,
    api_stats,
)

api_stats  # reason: FastAPI registers this decorated route.
api_sources  # reason: FastAPI registers this decorated route.
api_categories  # reason: FastAPI registers this decorated route.
api_files  # reason: FastAPI registers this decorated route.
api_file_detail  # reason: FastAPI registers this decorated route.
api_file_markdown  # reason: FastAPI registers this decorated route.

from ai_actuarial.api.routers.ready_data_automation import (
    api_set_ready_data_automation,
)

api_set_ready_data_automation  # reason: FastAPI registers this decorated route.

from ai_actuarial.api.routers.ready_data_publication import (
    api_publish_ready_data_publication,
    api_rollback_ready_data_publication,
)

api_publish_ready_data_publication  # reason: FastAPI registers this decorated route.
api_rollback_ready_data_publication  # reason: FastAPI registers this decorated route.

from ai_actuarial.api.routers.weekly_updates import (
    WeeklySnapshotFilesModel,
    api_weekly_explanation_detail,
    api_weekly_explanation_generate,
    api_weekly_explanation_latest,
    api_weekly_explanation_retry,
    api_weekly_update_detail,
    api_weekly_update_files,
    api_weekly_updates,
    api_weekly_updates_latest,
)

api_weekly_updates  # reason: FastAPI registers this decorated route.
api_weekly_updates_latest  # reason: FastAPI registers this decorated route.
api_weekly_explanation_latest  # reason: FastAPI registers this decorated route.
api_weekly_explanation_generate  # reason: FastAPI registers this decorated route.
api_weekly_explanation_retry  # reason: FastAPI registers this decorated route.
api_weekly_explanation_detail  # reason: FastAPI registers this decorated route.
api_weekly_update_files  # reason: FastAPI registers this decorated route.
api_weekly_update_detail  # reason: FastAPI registers this decorated route.
WeeklySnapshotFilesModel.truncated  # reason: Pydantic serializes this response field.

from ai_actuarial.web_listening_rule import (
    AcquisitionProfile,
    MonitorScope,
    MonitorTask,
    SectionSelection,
    WebListeningAgentRuleV1,
)

AcquisitionProfile._strip_required_text  # reason: Pydantic invokes this decorated validator.
AcquisitionProfile._normalize_file_exts  # reason: Pydantic invokes this decorated validator.
AcquisitionProfile._normalize_strategy_list  # reason: Pydantic invokes this decorated validator.
MonitorTask._strip_required_text  # reason: Pydantic invokes this decorated validator.
SectionSelection._strip_optional_text  # reason: Pydantic invokes this decorated validator.
SectionSelection._normalize_patterns  # reason: Pydantic invokes this decorated validator.
MonitorScope._normalize_string_list  # reason: Pydantic invokes this decorated validator.
WebListeningAgentRuleV1._validate_url_schedule_and_strategy  # reason: Pydantic invokes this decorated validator.

from ai_actuarial.api.middleware.rate_limit import RateLimitMiddleware

RateLimitMiddleware.dispatch  # reason: Starlette invokes the middleware protocol hook.

from ai_actuarial.collectors.base import CollectionConfig

CollectionConfig.auto_download  # reason: Public exported dataclass constructor field retained for compatibility.

from tests.agentic_rag.test_ready_data_builder import test_db_path
from tests.conftest import admin_token, guest_token, sample_task, sample_user
from tests.test_api_logging import restore_logging_state
from tests.test_fastapi_entrypoint import _hermetic_fastapi_env
from tests.test_recategory import env

test_db_path  # reason: Pytest injects this fixture by name.
admin_token  # reason: Pytest injects this fixture by name.
guest_token  # reason: Pytest injects this fixture by name.
sample_task  # reason: Pytest injects this fixture by name.
sample_user  # reason: Pytest injects this fixture by name.
restore_logging_state  # reason: Pytest injects this fixture by name.
_hermetic_fastapi_env  # reason: Pytest injects this fixture by name.
env  # reason: Pytest injects this fixture by name.
