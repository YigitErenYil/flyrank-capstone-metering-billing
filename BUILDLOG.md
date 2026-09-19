# Build Log — AI usage

Built with Claude assisting on design and implementation; I ran, tested, and
debugged everything locally and made the product/scope decisions.

## Where AI helped
- Drafted the initial `DESIGN.md` (schema, API contract, idempotency
  strategy) from the capstone brief.
- Wrote the FastAPI/SQLAlchemy scaffolding: `models.py`, `schemas.py`,
  `services/{metering,quota,cost,billing}.py`, `routers/*.py`.
- Wrote `fixtures/send_event.py` (self-signed webhook sender) once we hit
  the Stripe/Turkey account-creation block.

## Where it was wrong / needed a fix
- Initial `docker-compose.yml` didn't mount `seed.py` or `fixtures/` into
  the `api` container — `seed.py` failed with `No such file or directory`
  until the volume mounts were added.
- Assumed a Stripe test-mode account would be reachable from Turkey; had to
  pivot the whole Stripe integration to `stripe-mock` + self-signed fixture
  events after hitting the country-support wall (confirmed as an accepted
  path by FlyRank staff in the community — see screenshot below).

## What I changed / decided myself
- Chose the Pro plan quota numbers (10,000 calls / 1M tokens — 10x Free).
- Chose header-based idempotency (`Idempotency-Key`) over server-generated
  hashing.
- Ran every command myself (Docker, git init/push, curl tests, the fixture
  script) and fixed the local issues that came up (git repo not
  initialized, `cp` not available in Windows cmd, Stripe country selector).
- Decided on the stripe-mock + fixtures approach as the fallback once a real
  Stripe account turned out to be unavailable, based on FlyRank staff's
  community answer to another intern with the same problem (Pakistan case,
  same "Stripe doesn't support this country" situation):

  > "You are welcome to use any resources at your disposal to complete the
  > assignment and capstone. That means you can continue with this capstone
  > using the SDK with mocked/test fixtures, or you can choose another
  > capstone or alternative to Stripe." — FlyRank staff, community answer

I can walk through any 2-3 lines of this codebase and explain what they do
and why.
