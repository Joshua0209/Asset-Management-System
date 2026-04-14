# Requirements

**Project:** Asset Management System (資產管理系統)

---

## 1. Functional Requirements

### 1.1 Authentication & Authorization

| ID | Requirement | Role |
|----|------------|------|
| FR-01 | User registration with email and password | All |
| FR-02 | User login with session/token-based authentication | All |
| FR-03 | Role-based access control: Asset Holder vs. Asset Manager | All |
| FR-04 | Password reset via email | All |

### 1.2 Asset Basic Info Management (資產基礎資訊管理)

| ID | Requirement | Role |
|----|------------|------|
| FR-10 | Register new asset with auto-generated unique asset ID | Manager |
| FR-11 | Classify assets by category (phone, computer, tablet, etc.) | Manager |
| FR-12 | Record procurement details: name, model, specs, supplier, date, amount | Manager |
| FR-13 | Record detailed attributes: location, responsible person, department, activation date, warranty expiry | Manager |
| FR-14 | Track asset status (normal / under-repair) | System |
| FR-15 | Edit existing asset information | Manager |
| FR-16 | Assign/reassign asset to a holder (responsible person) | Manager |
| FR-17 | Multi-dimensional search and filter: by asset ID, name, model, location, person, status, department | Manager |
| FR-18 | Asset holder queries own assigned devices | Holder |

### 1.3 Repair Request Management (申請單管理)

| ID | Requirement | Role |
|----|------------|------|
| FR-20 | Submit repair request with asset ID, fault description, and optional photo upload | Holder |
| FR-21 | Prevent duplicate repair request for an asset already under repair | System |
| FR-22 | Review repair request: approve or reject | Manager |
| FR-23 | On approval: system sets asset status to "under-repair", request status to "under-repair" | System |
| FR-24 | On rejection: request status set to "rejected", workflow ends | System |
| FR-25 | Fill repair details: date, fault content, repair plan, cost, repair vendor/person | Manager |
| FR-26 | Mark repair complete: asset returns to "normal", request status to "completed" | Manager |
| FR-27 | Holder queries own repair request history with status | Holder |
| FR-28 | Manager queries all repair requests with filtering | Manager |
| FR-29 | Optimistic locking: when two managers edit the same request concurrently, only the first write succeeds; the second receives a conflict notification | System |

### 1.4 Image Upload

| ID | Requirement | Role |
|----|------------|------|
| FR-30 | Upload fault photos when submitting repair request (max 5 images, max 5 MB each) | Holder |
| FR-31 | View uploaded images on repair request detail page | All |

---

## 2. Non-Functional Requirements

| ID | Category | Requirement | Target |
|----|----------|------------|--------|
| NFR-01 | **Availability** | Core services remain functional during partial node failure | 99.9% uptime (three nines: < 8.77 hr downtime/year) |
| NFR-02 | **Scalability** | Architecture supports scaling from 300 to 3M DAU across three phases | Horizontal scaling of stateless tiers |
| NFR-03 | **Latency** | API response time for queries | P95 < 200ms (Phase 1-2), P95 < 500ms (Phase 3) |
| NFR-04 | **Latency** | Page render time | < 3 seconds |
| NFR-05 | **Security** | Authentication via JWT/session tokens; HTTPS everywhere; input validation at all boundaries; RBAC enforcement | OWASP Top 10 mitigated |
| NFR-06 | **Security** | SQL injection prevention via parameterized queries | 100% coverage |
| NFR-07 | **Observability** | Centralized logging, metrics collection, health checks, alerting | Detect anomalies within 1 minute |
| NFR-08 | **Deployment** | Zero-downtime deployment | Rolling update or blue-green strategy |
| NFR-09 | **Concurrency** | Optimistic locking on asset and repair request records | No silent data overwrites |
| NFR-10 | **i18n** | Multi-language UI support (Traditional Chinese, English minimum) | All user-facing text externalized |
| NFR-11 | **Data Integrity** | Daily automated backups with point-in-time recovery | RPO < 1 hour, RTO < 4 hours |
| NFR-12 | **Rate Limiting** | Protect API from abuse | 100 req/min per user (configurable) |
