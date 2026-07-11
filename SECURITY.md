# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it privately.

**Do not** open a public GitHub issue for security vulnerabilities.

### How to Report

- Open a GitHub Security Advisory on the repository
- Or contact the maintainer directly via the repository's discussion/contact channels

We will acknowledge receipt within 48 hours and provide a timeline for a fix.

## Scope

This project is a media downloader and surveillance monitoring tool. Security issues may include:

- **Authentication bypass** — accessing the admin panel without authorization
- **Path traversal** — reading/writing files outside the allowed directories
- **Command injection** — injecting commands via user-supplied URLs or filenames
- **Information disclosure** — leaking sensitive data in error messages or logs
- **CSRF/XSS** — cross-site attacks on admin endpoints

## Security Measures

- Admin authentication via hashed password (werkzeug) in environment variable
- Session-based authorization with HTTP-only cookies
- Rate limiting on all API endpoints
- Input validation on all user-supplied data
- Path traversal prevention on all file-serving routes
- SQL injection prevention via parameterized queries
- Security headers (X-Content-Type-Options, X-Frame-Options, X-XSS-Protection)
- CORS restricted to same origin
- MongoDB replication logging (optional, via MONGO_URI env var)

## Secure Deployment Checklist

- [ ] Set a strong `ADMIN_PASSWORD` environment variable
- [ ] Generate a unique `FLASK_SECRET_KEY`
- [ ] Run behind a reverse proxy (nginx/Caddy) with HTTPS
- [ ] Disable debug mode (`FLASK_DEBUG=0`)
- [ ] Restrict network access to the admin panel
- [ ] Regularly update dependencies
- [ ] Monitor access logs for unauthorized attempts
