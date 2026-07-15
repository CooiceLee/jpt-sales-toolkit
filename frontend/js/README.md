# Frontend module map

The frontend intentionally remains a dependency-free classic-script application. `app.js` is the entry file; business features live in `modules/`, and reusable DOM/format helpers live in `shared/`.

## Entry boundary

`app.js` owns only:

- shared application state and configuration loading;
- authentication startup;
- navigation and module routing;
- dashboard totals and the overview map.

Do not add feature CRUD, detail forms, data governance, trip-planning, or coordinate-maintenance code back to `app.js`.

## Module groups

- Intake: `intake-*`
- Stage worklists and cards: `stage-*`, `sales-worklists`, `service-worklists`, `card-*`, `cards`
- Sampling: `sampling-*`
- Inquiry detail: `inquiry-*`, `assignment-*`, `lead-closure`, `followups-*`, `aftersales-*`, `files-*`
- Governance and analysis: `customer-merge-*`, `data-transfer`, `data-governance`, `data-review*`
- Trip planning: `trip-*`, plus `lead-navigation`
- Coordinates: `coordinate-*`, `batch-geocode`
- Offline authorization: `authorization-*` (first-run activation and Leader-only member/device lifecycle)
- App chrome: `user-menu`, `refresh-counts`, `legacy-actions`

## Runtime contract

Scripts are loaded explicitly at the bottom of `frontend/index.html`. The application keeps browser-callable names on `window` because the current HTML uses inline handlers and modules call one another through the existing global contract.

When adding a module:

1. Keep it single-purpose and below 160 lines.
2. Export only the browser APIs that HTML or another module needs.
3. Escape every dynamic value written through `innerHTML`.
4. Add the script once in `frontend/index.html` after `app.js`.
5. Extend `test_frontend_module_contract.py` when introducing a new public browser API.
6. Run `bash scripts/validate_v08.sh` and complete a browser smoke test with temporary data.

The authorization boundary is deliberately provider-neutral in the UI. It consumes the
`/api/authorization/*` contract and keeps role choices limited to `leader`, `sales`, and
`tech`; Lead-level `owner`, `collaborator`, and `watcher` relationships remain business
assignments rather than installation roles.

## Future migration boundary

If the application later needs npm packages, route-level lazy loading, or multi-page builds, introduce a bundler as a separate migration. The current split keeps that option open without forcing a build dependency on the single-machine deployment today.
