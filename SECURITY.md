# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.1.x   | Yes       |
| < 1.1   | No        |

## Reporting a Problem

If you discover a security-related issue, **please do not open a public GitHub issue.**

Instead, email **dovik@micinthe.com** with:

- A description of the issue
- Steps to reproduce it
- The potential impact
- Any suggested fixes (if you have them)

You will receive an acknowledgment within 48 hours, and we will work with you to
understand and address the issue before any public disclosure.

## What Qualifies

- Authentication or authorization bypasses
- Prompt injection that circumvents the defense system
- Data exposure through the AI tools (accessing data beyond user permissions)
- Rate limiter bypasses
- Issues in the input sanitizer that could allow access to blocked DocTypes or fields

## What Does Not Qualify

- Issues in Frappe Framework or ERPNext core (report those upstream)
- Issues requiring physical access to the server
- Social engineering

## Responsible Disclosure

We ask that you give us reasonable time to address any reported issue before
making it public. We are committed to transparency and will credit reporters
in our changelog (unless they prefer to remain anonymous).

## Built-in Protections

This app includes multiple layers of protection:

- **Permission Guard** — enforces ERPNext role-based access on every AI tool call
- **Input Sanitizer** — blocks access to sensitive DocTypes and fields
- **Prompt Defense** — detects and blocks prompt injection patterns
- **Rate Limiter** — prevents abuse via per-user request limits
- **Audit Logging** — every AI tool call is logged for review
- **Field Whitelisting** — granular control over which fields the AI can access

Thank you for helping keep ERPNext AI Bots and its users safe.
