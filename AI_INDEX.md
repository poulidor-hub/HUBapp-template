# Index du Projet pour Assistant IA

> **Note pour l'IA** : Ceci est la carte du projet. Les numéros de ligne sont indiqués entre crochets. Demande un extrait de code spécifique (ex: Lignes 20 à 50) si tu as besoin de plus de contexte.

### 📄 `index_Test.py`
  - [Ligne 9] Fonction : def get_python_signatures()
  - [Ligne 25] Fonction : def get_react_components()
  - [Ligne 43] Fonction : def generate_index()

### 📄 `scripts/init_new_app.py`
  - [Ligne 29] Classe : class Colors
  - [Ligne 52] Fonction : def print_header()
  - [Ligne 71] Fonction : def get_project_root()
  - [Ligne 77] Fonction : def validate_slug()
  - [Ligne 82] Fonction : def validate_port()
  - [Ligne 91] Fonction : def prompt_input()
  - [Ligne 107] Fonction : def collect_app_info()
  - [Ligne 198] Fonction : def confirm_settings()
  - [Ligne 220] Fonction : def update_file()
  - [Ligne 256] Fonction : def create_env_file()
  - [Ligne 310] Fonction : def update_env_example()
  - [Ligne 351] Fonction : def update_docker_compose()
  - [Ligne 368] Fonction : def update_backend_config()
  - [Ligne 386] Fonction : def update_dockerfile_frontend()
  - [Ligne 400] Fonction : def update_frontend_index()
  - [Ligne 412] Fonction : def update_frontend_header()
  - [Ligne 424] Fonction : def update_frontend_package_json()
  - [Ligne 441] Fonction : def update_frontend_config_js()
  - [Ligne 453] Fonction : def update_test_fixtures()
  - [Ligne 491] Fonction : def cleanup_obsolete_files()
  - [Ligne 520] Fonction : def clean_demo_content()
  - [Ligne 569] Fonction : def _clean_models()
  - [Ligne 674] Fonction : def _clean_schemas()
  - [Ligne 904] Fonction : def _clean_main()
  - [Ligne 991] Fonction : def _clean_frontend_components()
  - [Ligne 1017] Fonction : def _clean_app_jsx()
  - [Ligne 1081] Fonction : def _clean_demo_tests()
  - [Ligne 1104] Fonction : def create_version_file()
  - [Ligne 1116] Fonction : def create_changelog()
  - [Ligne 1170] Fonction : def create_readme()
  - [Ligne 1271] Fonction : def setup_tailwind()
  - [Ligne 1319] Fonction : def _tailwind_update_package_json()
  - [Ligne 1342] Fonction : def _tailwind_create_configs()
  - [Ligne 1375] Fonction : def _tailwind_rewrite_css()
  - [Ligne 1432] Fonction : def _extract_message_css()
  - [Ligne 1467] Fonction : def _tailwind_rewrite_app_jsx()
  - [Ligne 1541] Fonction : def _tailwind_rewrite_header_jsx()
  - [Ligne 1621] Fonction : def _tailwind_rewrite_login_prompt_jsx()
  - [Ligne 1661] Fonction : def main()

### 📄 `scripts/bump_version.py`
  - [Ligne 37] Fonction : def read_version()
  - [Ligne 45] Fonction : def write_version()
  - [Ligne 51] Fonction : def parse_version()
  - [Ligne 60] Fonction : def bump_version()
  - [Ligne 75] Fonction : def update_package_json()
  - [Ligne 96] Fonction : def update_main_py()
  - [Ligne 126] Fonction : def update_api_docs()
  - [Ligne 178] Fonction : def update_env_versions()
  - [Ligne 214] Fonction : def check_changelog()
  - [Ligne 234] Fonction : def check_version_consistency()
  - [Ligne 291] Fonction : def sync_all()
  - [Ligne 305] Fonction : def show_usage()
  - [Ligne 310] Fonction : def generate_changelog_template()
  - [Ligne 341] Fonction : def main()

### 📄 `backend/storage.py`
  - [Ligne 23] Classe : class StorageManager

### 📄 `backend/models.py`
  - [Ligne 11] Classe : class Item
  - [Ligne 40] Classe : class UserPreference
  - [Ligne 66] Classe : class UploadedFile
  - [Ligne 133] Classe : class TestData

### 📄 `backend/config.py`
  - [Ligne 13] Fonction : def get_app_version()
  - [Ligne 29] Fonction : def get_docker_host_ip()
  - [Ligne 72] Fonction : def is_running_in_docker()
  - [Ligne 86] Fonction : def get_local_ip()
  - [Ligne 108] Classe : class Settings
  - [Ligne 226] Fonction : def get_settings()

### 📄 `backend/database.py`
  - [Ligne 16] Classe : class Base
  - [Ligne 78] Fonction : def _strip_sql_comments()

### 📄 `backend/hub_auth.py`
  - [Ligne 39] Classe : class RoleLevel
  - [Ligne 57] Fonction : def utcnow()
  - [Ligne 62] Fonction : def ensure_aware_utc()
  - [Ligne 70] Classe : class TokenPayload
  - [Ligne 98] Classe : class HubAuth
  - [Ligne 675] Fonction : def require_role()
  - [Ligne 709] Fonction : def require_any_role()
  - [Ligne 738] Fonction : def require_service_account()

### 📄 `backend/hub_client.py`
  - [Ligne 54] Classe : class DiscoveredService
  - [Ligne 76] Classe : class HubCredentials
  - [Ligne 84] Classe : class HubClient

### 📄 `backend/schemas.py`
  - [Ligne 11] Classe : class ItemBase
  - [Ligne 18] Classe : class ItemCreate
  - [Ligne 23] Classe : class ItemUpdate
  - [Ligne 30] Classe : class ItemResponse
  - [Ligne 43] Classe : class UserPreferenceBase
  - [Ligne 51] Classe : class UserPreferenceUpdate
  - [Ligne 59] Classe : class UserPreferenceResponse
  - [Ligne 71] Classe : class UserInfo
  - [Ligne 78] Classe : class TokenInfo
  - [Ligne 89] Classe : class MessageResponse
  - [Ligne 95] Classe : class PaginatedResponse
  - [Ligne 106] Classe : class DiscoveredServiceResponse
  - [Ligne 118] Classe : class DiscoveredServiceDetailResponse
  - [Ligne 128] Classe : class ServiceDiscoveryResponse
  - [Ligne 139] Classe : class UploadedFileBase
  - [Ligne 146] Classe : class UploadedFileCreate
  - [Ligne 152] Classe : class UploadedFileResponse
  - [Ligne 172] Classe : class BackupEstimate
  - [Ligne 193] Classe : class BackupMetadata
  - [Ligne 212] Classe : class BackupResponse
  - [Ligne 220] Classe : class RestoreRequest
  - [Ligne 229] Classe : class RestoreResponse
  - [Ligne 245] Classe : class SyncToHubRequest
  - [Ligne 251] Classe : class SyncFromHubRequest
  - [Ligne 259] Classe : class TestDataBase
  - [Ligne 266] Classe : class TestDataCreate
  - [Ligne 271] Classe : class TestDataUpdate
  - [Ligne 278] Classe : class TestDataResponse
  - [Ligne 289] Classe : class TestDataListResponse

### 📄 `backend/utils.py`
  - [Ligne 6] Fonction : def human_readable_size()
  - [Ligne 15] Fonction : def human_readable_duration()

### 📄 `backend/tests/test_backup.py`
  - [Ligne 28] Fonction : def temp_uploads_dir()
  - [Ligne 36] Fonction : def mock_storage_manager()
  - [Ligne 146] Classe : class TestStorageManager
  - [Ligne 287] Classe : class TestBackupEstimate
  - [Ligne 332] Classe : class TestBackupCreate
  - [Ligne 370] Classe : class TestBackupDownload
  - [Ligne 414] Classe : class TestBackupList
  - [Ligne 434] Classe : class TestBackupDelete
  - [Ligne 466] Classe : class TestRestore
  - [Ligne 608] Classe : class TestSyncToHub
  - [Ligne 628] Classe : class TestSyncFromHub
  - [Ligne 652] Classe : class TestBackupRestoreIntegration
  - [Ligne 686] Classe : class TestUploadedFileModel

### 📄 `backend/tests/conftest.py`
  - [Ligne 30] Fonction : def event_loop()
  - [Ligne 38] Fonction : def settings()
  - [Ligne 81] Fonction : def mock_hub_client()
  - [Ligne 92] Fonction : def mock_hub_auth()
  - [Ligne 100] Fonction : def create_mock_token()
  - [Ligne 202] Fonction : def mock_m2m_token()
  - [Ligne 226] Fonction : def mock_hub_client_with_m2m()

### 📄 `backend/tests/test_preferences.py`
  - [Ligne 8] Classe : class TestPreferences

### 📄 `backend/tests/test_m2m.py`
  - [Ligne 14] Classe : class TestM2MAuthentication
  - [Ligne 45] Classe : class TestM2MServiceDiscovery
  - [Ligne 66] Classe : class TestM2MEndpoints
  - [Ligne 91] Classe : class TestCrossServiceCommunication

### 📄 `backend/tests/test_items.py`
  - [Ligne 8] Classe : class TestItemsCRUD
  - [Ligne 147] Classe : class TestItemsValidation

### 📄 `backend/tests/test_auth.py`
  - [Ligne 8] Classe : class TestPublicEndpoints
  - [Ligne 42] Classe : class TestProtectedEndpoints
  - [Ligne 72] Classe : class TestRoleEndpoints

### 📄 `backend/tests/test_services.py`
  - [Ligne 14] Classe : class TestAllServicesEndpoint
  - [Ligne 70] Classe : class TestHubConnectionEndpoint
  - [Ligne 99] Classe : class TestSlugRecoveryEndpoint
  - [Ligne 123] Classe : class TestM2MServiceEndpoint
  - [Ligne 156] Classe : class TestSSEEndpoint
  - [Ligne 179] Classe : class TestBackupEndpoint
  - [Ligne 206] Classe : class TestSendTestMessageEndpoint
  - [Ligne 296] Classe : class TestSSEDemoEndpoint

### 📄 `backend/routes/docs.py`
  - [Ligne 16] Fonction : def get_changelog_path()
  - [Ligne 38] Fonction : def parse_changelog_versions()
  - [Ligne 62] Fonction : def extract_version_content()

### 📄 `backend/routes/backup.py`
  - [Ligne 67] Fonction : def _compute_checksum()
  - [Ligne 72] Fonction : def _serialize_value()
  - [Ligne 95] Fonction : def _deserialize_value()

### 📄 `backend/routes/tests.py`
  - [Ligne 39] Classe : class ServiceTestResult
  - [Ligne 48] Classe : class AllServicesTestResult
  - [Ligne 59] Classe : class SendTestMessageRequest
  - [Ligne 99] Classe : class SendTestMessageResult
  - [Ligne 121] Fonction : def _normalize_optional_text()
  - [Ligne 130] Fonction : def _normalize_target_usernames()

### ⚛️ `frontend/src/config.js`
  - [Ligne 8] Composant : APP_VERSION

### ⚛️ `frontend/src/App.jsx`
  - [Ligne 14] Composant : App

### ⚛️ `frontend/src/components/EndpointTests.jsx`
  - [Ligne 5] Composant : ENDPOINTS
  - [Ligne 16] Composant : EndpointTests

### ⚛️ `frontend/src/components/Header.jsx`
  - [Ligne 6] Composant : Header

### ⚛️ `frontend/src/components/TokenCard.jsx`
  - [Ligne 4] Composant : TokenCard

### ⚛️ `frontend/src/components/MessageArchive.jsx`
  - [Ligne 9] Composant : MessageArchive

### ⚛️ `frontend/src/components/M2MTests.jsx`
  - [Ligne 6] Composant : AVAILABLE_ENDPOINTS
  - [Ligne 105] Composant : ENDPOINT_CATEGORIES
  - [Ligne 107] Composant : M2MTests

### ⚛️ `frontend/src/components/DataTable.jsx`
  - [Ligne 7] Composant : CATEGORIES
  - [Ligne 9] Composant : DataTable

### ⚛️ `frontend/src/components/UserCard.jsx`
  - [Ligne 5] Composant : UserCard

### ⚛️ `frontend/src/components/MessageBanner.jsx`
  - [Ligne 11] Composant : MessageBanner

### ⚛️ `frontend/src/components/LoginPrompt.jsx`
  - [Ligne 4] Composant : LoginPrompt

### ⚛️ `frontend/src/context/ConfigContext.jsx`
  - [Ligne 4] Composant : ConfigContext
  - [Ligne 6] Composant : ConfigProvider

### ⚛️ `frontend/src/context/AuthContext.jsx`
  - [Ligne 5] Composant : AuthContext
  - [Ligne 69] Composant : AuthProvider

