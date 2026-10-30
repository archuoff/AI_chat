-- Register Engismart in the platform. Run once per environment on the PLATFORM database (MySQL; the statements are plain SQL and also work on PostgreSQL).
-- The platform's admin screens can do the same (Application + Roles); use whichever your team prefers.
-- Names must match the code: `engismart` = APP_ALIAS in controller/engismart/helper.py, router_outlet.py (track_module_usage) and constants.py (MODULE_NAMES);
-- `engismart_<domain>` = DOMAIN_PREFIX + the ids in controller/engismart/core/domains.py; the role aliases = ROLE_DEVELOPER / ROLE_SUPERUSER in the .env file.

-- 1. The application itself. Nobody gets into Engismart without it.
INSERT INTO tbl_application (category, sub_category, application_name, application_alias, token, under_maintenance, status, created_on)
VALUES ('AI', 'Knowledge', 'Engismart', 'engismart', 'b93bc18d-9ec8-4d46-b5d1-075f3a4bea2b', 0, 1, CURRENT_TIMESTAMP);

-- 2. One application row per domain. A normal user sees only the domains DevOps gives them (user or group permission screens).
--    A normal user without any of these rows is refused: every new user MUST be given at least one domain.
--    If these rows must not show on your home page or app list, set status = 0 after checking with the platform team how that list is built.
INSERT INTO tbl_application (category, sub_category, application_name, application_alias, token, under_maintenance, status, created_on)
VALUES ('AI', 'Engismart domain', 'Engismart - ADAS', 'engismart_adas', '3a3113e4-a364-5977-abb2-c3bec8ace249', 0, 1, CURRENT_TIMESTAMP);
INSERT INTO tbl_application (category, sub_category, application_name, application_alias, token, under_maintenance, status, created_on)
VALUES ('AI', 'Engismart domain', 'Engismart - Benchmarking', 'engismart_benchmarking', '3bab5cc2-7ad6-5955-abd1-59ead9408ee5', 0, 1, CURRENT_TIMESTAMP);
INSERT INTO tbl_application (category, sub_category, application_name, application_alias, token, under_maintenance, status, created_on)
VALUES ('AI', 'Engismart domain', 'Engismart - EDS', 'engismart_eds', '8f191c1c-79e8-5b70-b0d1-69b8bb72ca01', 0, 1, CURRENT_TIMESTAMP);
INSERT INTO tbl_application (category, sub_category, application_name, application_alias, token, under_maintenance, status, created_on)
VALUES ('AI', 'Engismart domain', 'Engismart - Lead Engineering', 'engismart_lead-engineering', '3d9478c3-4a52-57b7-8fa7-4be9018ce02b', 0, 1, CURRENT_TIMESTAMP);
INSERT INTO tbl_application (category, sub_category, application_name, application_alias, token, under_maintenance, status, created_on)
VALUES ('AI', 'Engismart domain', 'Engismart - Materials Net', 'engismart_materials-net', '604aa382-c537-5be8-9e38-f2fff1f70673', 0, 1, CURRENT_TIMESTAMP);
INSERT INTO tbl_application (category, sub_category, application_name, application_alias, token, under_maintenance, status, created_on)
VALUES ('AI', 'Engismart domain', 'Engismart - Supplier Database', 'engismart_supplier-database', 'cc4b67e3-8da2-5314-a971-05e34d7db210', 0, 1, CURRENT_TIMESTAMP);

-- 3. Two roles (no role = plain user). The alias (permission_alias) must be unique in the whole platform.
--      engismart_superuser : every domain + confidential documents + Manage knowledge
--      engismart_developer : the same + token usage and the plan in the answers
INSERT INTO tbl_application_roles (application_id, permission, token, permission_alias, created_on)
SELECT id, 'Engismart Developer', '67e5744e-f816-418d-8ff6-f2af9203a896', 'engismart_developer', CURRENT_TIMESTAMP FROM tbl_application WHERE application_alias = 'engismart';
INSERT INTO tbl_application_roles (application_id, permission, token, permission_alias, created_on)
SELECT id, 'Engismart Superuser', '7fc9e5e3-ba90-4e09-9798-53b527a436d9', 'engismart_superuser', CURRENT_TIMESTAMP FROM tbl_application WHERE application_alias = 'engismart';

-- 4. Then give people access with the platform's admin screens (users or groups):
--      application permission : the person (or group)  ->  Engismart                    (tbl_user_application_permission_map / tbl_group_application_permission_map)
--      application permission : the person (or group)  ->  Engismart - <domain> ...      one or more domains, for normal users
--      role                   : the person (or group)  ->  Engismart Superuser / Developer, only for those who need it
-- Superusers and developers see every domain; they do not need the domain rows. Platform admins act as developers (ADMIN_IS_DEVELOPER=true).
