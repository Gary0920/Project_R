# Intranet client updates through Project_R

Project_R's Windows client updates will be distributed through the Project_R backend on the company intranet rather than GitHub Releases or `electron-updater`'s full publishing flow. The backend owns version metadata and installer downloads, while the Electron main process owns downloading, SHA256 verification, progress reporting, and launching the installer.

**Status**: accepted

**Considered Options**: We considered GitHub Releases and the standard `electron-updater` path, but the internal deployment needs controlled LAN distribution, custom update copy, authenticated installer download, and no dependency on external release hosting.

**Consequences**: Update availability is checked against the current device's client version, not against user notification records; the notification center can expose the update entry point, but ordinary notification delivery does not decide whether a device must update.
