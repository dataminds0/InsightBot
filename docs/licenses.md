# Third-Party Dependencies and Licensing Obligations

This document tracks third-party components, tools, and libraries used in InsightBot, verifying their license compatibility with local self-hosted operation.

## Core Backend Dependencies

| Package | Version Baseline | License | Notes / Obligations |
|---|---|---|---|
| Python | 3.12 LTS | PSF License | Standard language runtime |
| FastAPI | >=0.115.0 | MIT | Requires copyright notice |
| Pydantic / Pydantic Settings | >=2.9.0 | MIT | Requires copyright notice |
| PyMongo | >=4.10.0 | Apache-2.0 | Apache attribution requirements |
| HTTPX | >=0.27.0 | BSD-3-Clause | BSD attribution requirements |
| Feedparser | >=6.0.11 | FreeBSD | Attribution requirements |
| Trafilatura | >=1.12.0 | Apache-2.0 | Text extraction; Apache attribution |
| Typer | >=0.12.5 | MIT | CLI framework |
| Argon2-cffi / Bcrypt | Recent | MIT / Apache-2.0 | Cryptographic password hashing |
| Ruff / Mypy / Pytest | Recent | MIT / Apache-2.0 | Development and testing toolchain |

## Core Infrastructure

| Component | License | Notes / Obligations |
|---|---|---|
| MongoDB Community | Server Side Public License (SSPL) | Source-available; self-hosted local usage permitted |
| Prefect | Apache-2.0 | Local workflow orchestration |

## Frontend Dependencies

| Package | Version Baseline | License | Notes / Obligations |
|---|---|---|---|
| React & React-DOM | ^18.3.1 | MIT | Standard web UI runtime |
| Vite | ^6.0.0 | MIT | Build tool and dev server |
| TypeScript | ~5.6.3 | Apache-2.0 | Language toolchain |
| Tailwind CSS | ^3.4.16 | MIT | Utility styling |
| TanStack React Query | ^5.62.0 | MIT | Client state and caching |
| Lucide React | ^0.468.0 | ISC | Icon library |

---
*Maintained under task T01 according to the development and implementation plan.*
