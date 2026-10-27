-- Register Engismart in the platform (run once per environment, on the PLATFORM database).
-- The platform's admin screens can do the same (Application + Roles); use whichever your team prefers.
-- The alias must match: router_outlet.py (track_module_usage), constants.py (MODULE_NAMES) and services/engismart/access.py (APP_ALIAS).

INSERT INTO tbl_application (category, sub_category, application_name, application_alias, token, under_maintenance, status, created_on)
VALUES ('AI', 'Knowledge', 'Engismart', 'engismart', 'b93bc18d-9ec8-4d46-b5d1-075f3a4bea2b', 0, 1, CURRENT_TIMESTAMP);

-- Three roles. The alias (permission_alias) must be unique in the whole platform and must equal ROLE_DEVELOPER / ROLE_SUPERUSER / ROLE_USER in the .env file.
INSERT INTO tbl_application_roles (application_id, permission, token, permission_alias, created_on)
SELECT id, 'Engismart Developer', '67e5744e-f816-418d-8ff6-f2af9203a896', 'engismart_developer', CURRENT_TIMESTAMP FROM tbl_application WHERE application_alias = 'engismart';
INSERT INTO tbl_application_roles (application_id, permission, token, permission_alias, created_on)
SELECT id, 'Engismart Superuser', '7fc9e5e3-ba90-4e09-9798-53b527a436d9', 'engismart_superuser', CURRENT_TIMESTAMP FROM tbl_application WHERE application_alias = 'engismart';
INSERT INTO tbl_application_roles (application_id, permission, token, permission_alias, created_on)
SELECT id, 'Engismart User', '19d049ed-a47a-4c33-831c-b2905104b6ac', 'engismart_user', CURRENT_TIMESTAMP FROM tbl_application WHERE application_alias = 'engismart';

-- Then give people access (users or groups) with the platform's admin screens:
--   1. application permission:  user (or group)  ->  Engismart          (tbl_user_application_permission_map / tbl_group_application_permission_map)
--   2. role:                    user (or group)  ->  one of the 3 roles  (tbl_application_user_role_permission / tbl_group_application_role_map)
-- Someone with the application but no role is treated as a plain "user". Platform admins act as developers (ADMIN_IS_DEVELOPER=true).
