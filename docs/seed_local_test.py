"""Local test setup WITHOUT the real platform database: creates the platform tables and a few test users in an EMPTY database.

Use it only on your own test database (for example a local PostgreSQL). It refuses to run when tbl_users already has rows,
so it cannot touch a real platform database.

    1. .env.development: DATABASE_HOST / PORT / USER / PASSWORD / NAME of the EMPTY test database (PostgreSQL: DATABASE_PORT=5432)
    2. from the project root:   uv run python docs/engismart/seed_local_test.py
    3. start the app (uv run run.py) and log in with one of the users below

Users (password for all: Test@1234)
    dev_user     role Engismart Developer       every domain, Manage knowledge, token usage
    super_user   role Engismart Superuser       every domain, Manage knowledge
    adas_user    no role, domain ADAS only      chat only
    eds_user     no role, domain EDS only       chat only
    nodomain     no role, no domain             refused (403): shows the "no domain" rule
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())

from werkzeug.security import generate_password_hash  # noqa: E402

from models.model import models  # noqa: E402
from models.orm_models import (  # noqa: E402
    Application,
    ApplicationRole,
    ApplicationUserRolePermission,
    Base,
    User,
    UserApplicationPermissionMap,
    engine,
)

PASSWORD = "Test@1234"
DOMAINS = ["adas", "benchmarking", "eds", "lead-engineering", "materials-net", "supplier-database"]


def main() -> None:
    print("Database:", engine.url.render_as_string(hide_password=True))
    Base.metadata.create_all(bind=engine)  # every platform table + tbl_engismart_image (the chat-memory tables come with the first chat)
    now = datetime.now()
    with models() as db:
        s = db.session
        if s.query(User).count() > 0:
            sys.exit("tbl_users already has rows: this is not an empty test database. Nothing was changed.")
        apps = {}
        for alias, name in [("engismart", "Engismart")] + [(f"engismart_{d}", f"Engismart - {d}") for d in DOMAINS]:
            apps[alias] = Application(category="AI", sub_category="Engismart", application_name=name, application_alias=alias,
                                      token=f"local-{alias}", under_maintenance=0, status=1, created_on=now)
            s.add(apps[alias])
        s.flush()
        roles = {}
        for alias, name in (("engismart_developer", "Engismart Developer"), ("engismart_superuser", "Engismart Superuser")):
            roles[alias] = ApplicationRole(application_id=apps["engismart"].id, permission=name, token=f"local-{alias}",
                                           permission_alias=alias, created_on=now)
            s.add(roles[alias])
        s.flush()

        def user(username, domain_aliases=(), role=None):
            u = User(username=username, display_name=username, email=f"{username}@local.test", token=f"local-user-{username}",
                     password=generate_password_hash(PASSWORD), is_admin="0", authentication_type="normal", approved=1, status=1,
                     is_deleted=0, token_version=1, login_count=0, created_on=now)
            s.add(u)
            s.flush()
            for a in ("engismart", *domain_aliases):
                s.add(UserApplicationPermissionMap(user_id=u.id, application_id=apps[a].id, created_on=now))
            if role:
                s.add(ApplicationUserRolePermission(user_id=u.id, application_role_id=roles[role].id, created_on=now))

        user("dev_user", role="engismart_developer")
        user("super_user", role="engismart_superuser")
        user("adas_user", ["engismart_adas"])
        user("eds_user", ["engismart_eds"])
        user("nodomain")
        s.commit()
    print("Done. Users dev_user, super_user, adas_user, eds_user, nodomain; password", PASSWORD)


if __name__ == "__main__":
    main()
