(json_access_log) {
	log {
		output file /data/access.log {
			roll_size 50MiB
			roll_keep 5
		}
		format json
	}
}

(baseline_security_headers) {
	header {
		defer
		X-Content-Type-Options "nosniff"
		X-Frame-Options "DENY"
		Referrer-Policy "strict-origin-when-cross-origin"
		Permissions-Policy "geolocation=(), microphone=(), camera=()"
	}
}

(app_security_headers) {
	import baseline_security_headers
	map {env.CONTENT_SECURITY_POLICY} {app_content_security_policy} {
		"" "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; img-src 'self' data: blob: https:; font-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self' ws: wss:"
		default "{env.CONTENT_SECURITY_POLICY}"
	}
	header {
		defer
		Content-Security-Policy "{app_content_security_policy}"
		Strict-Transport-Security "max-age=31536000"
	}
}

http://:80 {
	@health host localhost
	handle @health {
		respond "ok" 200
	}

	@app_redirect_hosts host {$CADDY_APP_REDIRECT_HOSTS:localhost}
	handle @app_redirect_hosts {
		redir {$CADDY_APP_REDIRECT_ORIGIN:https://localhost}{uri} 308
	}

	respond "" 421
}

{$CADDY_APP_SITE_HOSTS:http://localhost:8080} {
	import json_access_log
	import app_security_headers
	encode zstd gzip

	@hashed_assets path_regexp hashed_asset ^/assets/.+-[A-Za-z0-9_-]{8}\.[A-Za-z0-9.]+$
	header @hashed_assets {
		defer
		Cache-Control "public, max-age=31536000, immutable"
		match status 200 206
	}

	@asset_paths path /assets/*
	header @asset_paths {
		defer
		Cache-Control "no-store"
		match status 300 301 302 303 305 306 307 308 4xx 5xx
	}

	header {
		defer
		Cache-Control "no-cache"
		match {
			status 2xx
			header Content-Type text/html*
		}
	}

	handle /api/* {
		reverse_proxy api:5000
	}

	handle /assets/* {
		reverse_proxy frontend:5173 {
			header_up -If-None-Match
			header_up -If-Modified-Since
			@spa_fallback {
				status 2xx
				header Content-Type text/html*
			}
			handle_response @spa_fallback {
				respond "Not Found" 404
			}
		}
	}

	handle {
		reverse_proxy frontend:5173
	}
}
