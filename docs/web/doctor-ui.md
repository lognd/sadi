# Doctor UI

Status: current

The web app has a Doctor screen (`web/src/doctor/DoctorScreen.tsx`) that mirrors
`sadi doctor` (see [doctor.md](../doctor.md)).

- Lists every check with its status, title and headline.
- Checks with a remediation expand into numbered fix steps with copy-paste commands and expected output.
- Each check has a Re-run button that calls `POST /api/doctor/{check_id}/run` and replaces the row.
- A persistent "Doctor" button in `App.tsx` opens it from any wizard step; a failed health probe
  opens it automatically via `openDoctorOnConnectionError()` (`useDoctorRoute.ts`).

## API contract

The typed client (`web/src/api/client.ts`) expects `GET /api/doctor` (a `DoctorReport`) and
`POST /api/doctor/{check_id}/run` (a `CheckResult`). Types in `web/src/doctor/types.ts` mirror
`python/sadi/doctor/schema.py`. The server implements both in `python/sadi/server/routes_doctor.py` (`make_doctor_router()`): checks run in a threadpool, the doctor is read-only, and an unknown check id returns HTTP 404. The app factory (not yet present) mounts it alongside the plugin routes.
