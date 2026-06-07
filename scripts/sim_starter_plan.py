"""One-shot: simula plan Starter en una cuenta sin pago real.

- Box: asigna Subscription(plan_id=starter, status=active) al EditorUser
  vinculado por account_email, resetea contadores diarios.
- Web: pone nebulabs:user.planId="starter" (display + canSchedule + corta
  el decremento de trial).

Uso: python scripts/sim_starter_plan.py <account_email>
"""

from __future__ import annotations

import sys

from src.editor_auto.models.billing import Subscription, UsageStats
from src.editor_auto.repos import PlanRepo, UserRepo
from src.editor_auto.repos.web_account_repo import get_web_account_repo


def main() -> int:
    email = (sys.argv[1] if len(sys.argv) > 1 else "ness4b@gmail.com").strip().lower()

    plan = PlanRepo().get_by_slug("starter")
    if not plan:
        print("ERROR: no existe plan slug 'starter' en el box (¿seeder corrió?)")
        return 1
    print(f"plan starter: id={plan.id} limit/dia={plan.daily_video_limit} tools={plan.allowed_tools}")

    repo = UserRepo()
    user = repo.get_by_account_email(email)
    if not user:
        print(f"ERROR: no hay EditorUser vinculado a account_email={email}")
        return 1

    user.subscription = Subscription(plan_id=plan.id, status="active", notes="SIM Starter (sin pago)")
    user.usage = UsageStats()  # reset diario/mensual a 0
    repo.save(user)
    print(f"box OK: user={user.name} id={user.id} sub=starter active, usage reset")

    web = get_web_account_repo()
    acc = web.set_plan(email, "starter")
    if acc:
        print(f"web OK: planId={acc.get('planId')} trialVideos={acc.get('trialVideos')}")
    else:
        print("WARN: cuenta web no encontrada (planId no seteado)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
