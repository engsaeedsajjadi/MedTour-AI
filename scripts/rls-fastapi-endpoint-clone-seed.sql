-- Synthetic fixtures for FastAPI/RLS HTTP proof. MUST run only in disposable clone.
\set ON_ERROR_STOP on
BEGIN;
DO $clone_guard$
BEGIN
 IF current_database()<>'medtour_principal_clone' OR current_user<>'postgres' THEN
   RAISE EXCEPTION 'Refusing fixture insertion outside disposable PostgreSQL clone';
 END IF;
END $clone_guard$;
INSERT INTO public.users(id,tenant_id,email,password_hash,role,active,created_at)
VALUES ('__USER_A__','__TENANT_A__','admin-a@synthetic.invalid','not-for-login','admin',TRUE,now()),
('__USER_B__','__TENANT_B__','admin-b@synthetic.invalid','not-for-login','admin',TRUE,now()),
('__AUDITOR_A__','__TENANT_A__','auditor-a@synthetic.invalid','not-for-login','auditor',TRUE,now());
INSERT INTO public.portal_access(id,tenant_id,patient_id,token_hash,expires_at,revoked,issued_by,created_at)
VALUES ('__PORTAL_ID_A__','__TENANT_A__','__PATIENT_A__','__HASH_PORTAL_A__',now()+interval '2 hours',FALSE,'__USER_A__',now()),
('__PORTAL_ID_B__','__TENANT_B__','__PATIENT_B__','__HASH_PORTAL_B__',now()+interval '2 hours',FALSE,'__USER_B__',now());
INSERT INTO public.patient_consent_challenges(id,tenant_id,patient_id,token_hash,purpose,expires_at,issued_by,created_at)
VALUES ('__CONSENT_ID_A__','__TENANT_A__','__PATIENT_A__','__HASH_CONSENT_A__','communication',now()+interval '2 hours','__USER_A__',now()),
('__CONSENT_ID_B__','__TENANT_B__','__PATIENT_B__','__HASH_CONSENT_B__','communication',now()+interval '2 hours','__USER_B__',now());
INSERT INTO public.refresh_sessions(id,tenant_id,user_id,refresh_hash,expires_at,family_id,created_at)
VALUES ('__REFRESH_ID_A__','__TENANT_A__','__USER_A__','__HASH_REFRESH_A__',now()+interval '2 hours','__FAMILY_A__',now()),
('__REFRESH_ID_B__','__TENANT_B__','__USER_B__','__HASH_REFRESH_B__',now()+interval '2 hours','__FAMILY_B__',now());
COMMIT;
