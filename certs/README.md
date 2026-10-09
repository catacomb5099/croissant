Drop extra root CA certificates here as `*.pem` (gitignored) and they are appended to the image's
trust bundle at build time, so `pip`, Discogs and YouTube Music calls all verify behind a
TLS-intercepting corporate proxy. On a normal network leave this folder as it is.
