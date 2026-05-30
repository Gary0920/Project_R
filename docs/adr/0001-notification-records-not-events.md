# Notification records over notification events

Project_R's first notification-center implementation will extend the existing per-user `Notification` record model instead of introducing a separate `NotificationEvent` table. Broadcasts are expanded into one notification record per recipient so each user can have independent read and action status, and ordinary workspace file activity stays in workspace activity rather than the global notification center.

**Status**: accepted

**Considered Options**: We considered a shared event table with recipient records, but for a 50-person internal deployment the extra normalization is not worth the first-version complexity.

**Consequences**: The first version may duplicate event text across recipient rows, but API authorization, read state, pending action state, cleanup, and future notification preferences remain simple.
