# Mobile integration notes

Base URL configurable (Android device host reachable API), root /v1. Bearer Authorization on personal requests including image content. Follow Foundation contracts/API_CONTRACT.md DTOs; main owns OpenAPI and generates packages/api-client/src/schema.d.ts.

Catalog: {catalog_version,runtime_mode:'production'|'development',crops:[{id,name_ru,support_status:'unavailable'|'development'|'validated',can_assess,supported_organs:string[],model_version:string|null,availability_reason:string|null,classes:[{class_id,condition_id}]}]}. Dev synthetic supports wheat,potato,tomato leaf only, conspicuous demo banner, inconclusive only. No model in prod: can_assess false, reason model_unavailable. Maize unsupported.
Me: {id:string,display_name:string|null}; id stable server actor UUID.
ObservationCreate per Foundation, field_season_id null only first version; ObservationRead {id,client_observation_id,crop_id,organ,captured_at,notes,created_at,photos:PhotoRead[],assessments:AssessmentRead[]}.
History GET /v1/observations?cursor=&limit=20 -> {items:ObservationRead[],next_cursor:string|null}; filters crop_id, from,to. POST /v1/observations -> same ObservationRead. Known can_assess=false may save observation+photo only.
PhotoUpload: multipart client_photo_id UUID, purpose primary/context, file; PhotoRead {id,observation_id,purpose,status,media_type,width,height,sha256,created_at}. content-url -> {url,expires_at}; url is relative /v1/photos/{id}/content?expires=...&signature=... (resolve base origin) and STILL requires bearer header.
Assessment create/poll exactly Foundation. Errors {code,message,details,request_id}. IDs/keys stable through online retries. Feedback endpoint will be included if affordable, DTO {helpful:boolean|null,suspected_error:boolean=false,note:string|null}; no annotations.
Auth: production OIDC using Expo AuthSession code+PKCE; discovery/issuer/clientId configurable. In explicit local development allow operator-entered bearer token (backend scripts create dev signed token with 24h expiry); never UUID-as-auth. Show development auth banner; do not store arbitrary plaintext token. Main delivers .env public config keys coordinated with agent.

You own apps/mobile, packages/api-client transport if needed, root package.json/pnpm-workspace.yaml/pnpm-lock.yaml. Do not own generated schema.d.ts or backend. Request API schema when ready; do not handwrite generated DTOs. You may temporarily import type-only contracts locally but replace with generated schema before final.
No web UI; optional Expo export used as build artifact check only, not implement web pages.
