# FishKids production deployment

The existing VDS uses /home/desai/backend and /home/desai/frontend as source checkouts, Docker Compose 1.29 and SQLite.

- Runtime secrets belong only in /home/desai/deploy/.env.backend, mode 600.
- /home/desai/frontend/.env contains only public VITE_BACKEND_URL and VITE_YMAPS_API_KEY, mode 600.
- Production compose binds backend data.sqlite3, media and static, not application source.
- Published container ports bind to 127.0.0.1. Public traffic goes through HTTPS Nginx.
- /media/files/ is authenticated by Django; /_protected_courses/ is an internal-only Nginx alias.
- Native video/download links are signed, expire after one hour and are checked against current enrollment and session revocation.
- The deployment script builds immutable candidate images from fetched commits before stopping the backend, requires successful CI and never resets tracked source changes.
- The systemd timer can continue using /home/desai/deploy/deploy.sh every 15 minutes. GitHub deployment is manual to avoid two deployment mechanisms racing.
- Database backups and payment reservation/reconciliation are outside this update's authorized scope.
- Do not run this deployment until a working SMTP sender has been configured and verified. Existing customers must confirm email after the update.

For the initial migration, preserve the existing domain settings in service/settings.py, resolve the known untracked frontend Dockerfile/nginx configuration against the committed equivalents, and check the SQLite preflight before activating the new script.
