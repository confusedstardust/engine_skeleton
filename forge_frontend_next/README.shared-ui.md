# Shared account UI

`@narrativeos/ui` supplies the account menu, administrator permission link, icons, styles, account client, session hook and compact logo. Components in this app adapt Next navigation and backend URLs; they do not duplicate the shared implementation.

The maintained source is in the portal repository at `linchangWeb/packages/narrativeos-ui`. This app installs the versioned npm archive in `vendor/`, pinned by `package-lock.json`, so a checkout and Docker build are self-contained.

To update, bump the shared package version, run `npm pack --pack-destination <this-directory>/vendor` from its source directory, and run `npm install ./vendor/narrativeos-ui-<version>.tgz` here. Commit the archive, manifest and lockfile together. Do not edit `node_modules` or fork the account menu into a page.

Next `Link` adds the configured base path, so its `href` values remain `/history`, `/admin`, etc. API calls and plain anchors use `withBasePath`. Preserve this distinction when adding links.

The Dockerfile copies `vendor` before `npm ci`; Next transpiles the shared TypeScript package and the root layout imports its shared CSS. Existing app-specific navigation styles remain in `app/globals.css`.
