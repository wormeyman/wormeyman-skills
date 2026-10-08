<?php
/**
 * Plugin Name: Tracker Audit Probe
 * Description: Inventory for a tracker and consent audit. Makes no changes itself; database writes by the hook code it runs are rolled back, with the exceptions its response lists. Administrators only. Stops answering 48 hours after upload. Delete this file when the audit is done.
 * Version: 1.0.0
 * Requires PHP: 8.0
 *
 * Upload to wp-content/mu-plugins/. Call GET /wp-json/tracker-audit/v1/inventory
 * with an administrator's Application Password. It never returns users,
 * comments, subscribers, form entries or option values beyond matched tracker IDs.
 */

defined( 'ABSPATH' ) || exit;

const TRACKER_AUDIT_PROBE_VERSION = '1.0.0';
const TRACKER_AUDIT_PROBE_HOURS   = 48;

function tracker_audit_probe_age_hours(): float {
	return ( time() - (int) filemtime( __FILE__ ) ) / HOUR_IN_SECONDS;
}

function tracker_audit_probe_expired(): bool {
	// Fails closed: a file time in the future (clock skew, a copied timestamp) counts as expired too.
	$age = tracker_audit_probe_age_hours();
	return $age < 0 || $age > TRACKER_AUDIT_PROBE_HOURS;
}

add_action( 'admin_notices', function () {
	if ( ! current_user_can( 'manage_options' ) ) {
		return;
	}
	$state = tracker_audit_probe_expired() ? 'has expired' : 'is active';
	printf(
		'<div class="notice notice-warning"><p>The tracker audit probe %s. Delete <code>wp-content/mu-plugins/%s</code> when the audit is done.</p></div>',
		esc_html( $state ),
		esc_html( wp_basename( __FILE__ ) )
	);
} );

add_action( 'rest_api_init', function () {
	register_rest_route( 'tracker-audit/v1', '/inventory', array(
		'methods'             => 'GET',
		'callback'            => 'tracker_audit_probe_inventory',
		'show_in_index'       => false,
		'permission_callback' => function () {
			if ( ! is_user_logged_in() ) {
				return new WP_Error( 'rest_not_logged_in', 'Sign in with an administrator Application Password.', array( 'status' => 401 ) );
			}
			return current_user_can( 'manage_options' )
				? true
				: new WP_Error( 'rest_forbidden', 'Administrators only.', array( 'status' => 403 ) );
		},
	) );
} );

/** Tracker IDs in a piece of text, by kind. */
function tracker_audit_probe_ids( string $text ): array {
	$patterns = array(
		'ga4'        => '/\bG-[A-Z0-9]{6,12}\b/',
		'ua'         => '/\bUA-\d{4,10}-\d{1,4}\b/',
		'gtm'        => '/\bGTM-[A-Z0-9]{4,10}\b/',
		'google_ads' => '/\bAW-\d{6,12}\b/',
		'meta_pixel' => '/fbq\(\s*[\'"]init[\'"]\s*,\s*[\'"](\d{8,20})/',
		'clarity'    => '/clarity\.ms\/tag\/([a-z0-9]{6,14})|[\'"]clarity[\'"]\s*,\s*[\'"]script[\'"]\s*,\s*[\'"]([a-z0-9]{6,14})[\'"]/',
		'hotjar'     => '/hjid\s*:\s*(\d{5,10})/',
		'pinterest'  => '/pintrk\(\s*[\'"]load[\'"]\s*,\s*[\'"](\d{10,16})/',
		'tiktok'     => '/ttq\.load\(\s*[\'"]([A-Z0-9]{15,25})/',
	);
	$found = array();
	foreach ( $patterns as $kind => $re ) {
		if ( ! preg_match_all( $re, $text, $matches, PREG_SET_ORDER ) ) {
			continue;
		}
		foreach ( $matches as $hit ) {
			// The last non-empty group is the ID; patterns with no group use the whole match.
			for ( $i = count( $hit ) - 1; $i >= 0; $i-- ) {
				if ( '' !== $hit[ $i ] ) {
					$found[ $kind ][] = $hit[ $i ];
					break;
				}
			}
		}
	}
	return array_map( fn( $ids ) => array_values( array_unique( $ids ) ), $found );
}

/** Third-party hosts named in printed markup, including //host and JSON-escaped URLs. */
function tracker_audit_probe_domains( string $html ): array {
	$html = str_replace( '\/', '/', $html );
	preg_match_all( '#(?:https?:)?//([a-z0-9.-]+\.[a-z]{2,})#i', $html, $m );
	$own   = (string) wp_parse_url( home_url(), PHP_URL_HOST );
	$hosts = array_unique( array_map( 'strtolower', $m[1] ) );
	return array_values( array_filter( $hosts, fn( $h ) => $h !== $own ) );
}

function tracker_audit_probe_owner_of_file( string $file ): string {
	if ( '' === $file ) {
		return 'internal';
	}
	$file  = wp_normalize_path( $file );
	$roots = array(
		'mu-plugin' => wp_normalize_path( WPMU_PLUGIN_DIR ),
		'plugin'    => wp_normalize_path( WP_PLUGIN_DIR ),
		'theme'     => wp_normalize_path( get_theme_root() ),
	);
	foreach ( $roots as $kind => $root ) {
		if ( str_starts_with( $file, $root . '/' ) ) {
			return $kind . ':' . strtok( substr( $file, strlen( $root ) + 1 ), '/' );
		}
	}
	return str_starts_with( $file, wp_normalize_path( ABSPATH ) ) ? 'core' : 'other';
}

/** Readable name, defining file and owner of a hooked callback. */
function tracker_audit_probe_describe( $callback ): array {
	try {
		if ( is_string( $callback ) && str_contains( $callback, '::' ) ) {
			$callback = explode( '::', $callback, 2 );
		}
		if ( is_array( $callback ) ) {
			$ref  = new ReflectionMethod( $callback[0], $callback[1] );
			$name = ( is_object( $callback[0] ) ? get_class( $callback[0] ) : $callback[0] ) . '::' . $callback[1];
		} elseif ( $callback instanceof Closure || is_string( $callback ) ) {
			$ref  = new ReflectionFunction( $callback );
			$name = is_string( $callback ) ? $callback : 'closure';
		} elseif ( is_object( $callback ) && method_exists( $callback, '__invoke' ) ) {
			$ref  = new ReflectionMethod( $callback, '__invoke' );
			$name = get_class( $callback ) . '::__invoke';
		} else {
			return array( 'name' => 'unknown', 'file' => '', 'owner' => 'unknown' );
		}
	} catch ( Throwable $e ) {
		return array( 'name' => 'unknown', 'file' => '', 'owner' => 'unknown' );
	}
	$file = (string) $ref->getFileName();
	$rel  = str_starts_with( wp_normalize_path( $file ), wp_normalize_path( ABSPATH ) )
		? substr( wp_normalize_path( $file ), strlen( wp_normalize_path( ABSPATH ) ) )
		: $file;
	return array( 'name' => $name, 'file' => $rel, 'owner' => tracker_audit_probe_owner_of_file( $file ) );
}

/** Run each callback on a hook by itself, capturing what it prints and enqueues. */
function tracker_audit_probe_run_hook( string $hook ): array {
	global $wp_filter, $wp_scripts;
	$out = array();
	if ( empty( $wp_filter[ $hook ] ) ) {
		return $out;
	}
	foreach ( $wp_filter[ $hook ]->callbacks as $priority => $callbacks ) {
		foreach ( $callbacks as $cb ) {
			$entry             = tracker_audit_probe_describe( $cb['function'] );
			$entry['priority'] = (int) $priority;
			$before            = $wp_scripts instanceof WP_Scripts ? $wp_scripts->queue : array();
			if ( ! headers_sent() ) {
				// If a callback calls exit, this header names it and its owner in the cut-short response.
				$current = preg_replace( '/[^\w:\\\\. -]/', '', $hook . ' ' . $entry['owner'] . ' ' . $entry['name'] );
				header( 'X-Tracker-Audit-Current: ' . substr( (string) $current, 0, 200 ) );
			}
			$level = ob_get_level();
			ob_start();
			try {
				$args = $cb['accepted_args'] > 0 ? array_fill( 0, (int) $cb['accepted_args'], '' ) : array();
				call_user_func_array( $cb['function'], $args );
				$entry['status'] = 'ok';
			} catch ( Throwable $e ) {
				$entry['status'] = 'error: ' . get_class( $e );
			}
			$html = '';
			while ( ob_get_level() > $level ) {
				// A buffer that cannot be removed would spin forever; stop and say so.
				$prev  = ob_get_level();
				$chunk = ob_get_clean();
				if ( false === $chunk || ob_get_level() >= $prev ) {
					$entry['status'] = 'error: unremovable output buffer';
					break;
				}
				$html = $chunk . $html;
			}
			$after = $wp_scripts instanceof WP_Scripts ? $wp_scripts->queue : array();
			$added = array_values( array_diff( $after, $before ) );
			if ( $added ) {
				$entry['enqueued'] = array();
				foreach ( $added as $handle ) {
					$entry['enqueued'][ $handle ] = (string) ( $wp_scripts->registered[ $handle ]->src ?? '' );
				}
			}
			if ( preg_match( '/<(script|iframe|noscript|img)\b/i', $html ) ) {
				$entry['prints'] = array(
					'domains' => tracker_audit_probe_domains( $html ),
					'ids'     => tracker_audit_probe_ids( $html ),
					'excerpt' => mb_substr( trim( $html ), 0, 300 ),
				);
			}
			$out[] = $entry;
		}
	}
	return $out;
}

/** Option names whose value holds a tracker ID, with the IDs only. */
function tracker_audit_probe_options(): array {
	global $wpdb;
	$needles = array( 'G-', 'UA-', 'GTM-', 'AW-', 'fbq(', 'clarity', 'hjid', 'pintrk', 'ttq.load' );
	$where   = implode( ' OR ', array_map(
		fn( $s ) => $wpdb->prepare( 'option_value LIKE %s', '%' . $wpdb->esc_like( $s ) . '%' ),
		$needles
	) );
	$rows = $wpdb->get_results( "SELECT option_name, option_value FROM {$wpdb->options} WHERE option_name NOT LIKE '%transient%' AND ( {$where} )" );
	$out  = array();
	foreach ( $rows as $row ) {
		$ids = tracker_audit_probe_ids( (string) $row->option_value );
		if ( $ids ) {
			$out[ $row->option_name ] = $ids;
		}
	}
	return $out;
}

/** Known consent plugins: installed, active, and which option names exist (no values). */
function tracker_audit_probe_consent(): array {
	global $wpdb;
	$known   = array(
		'WPConsent'          => array( 'wpconsent-cookies-banner-privacy-suite', 'wpconsent' ),
		'Complianz'          => array( 'complianz-gdpr', 'cmplz' ),
		'CookieYes'          => array( 'cookie-law-info', 'cky' ),
		'Cookie Notice'      => array( 'cookie-notice', 'cookie_notice' ),
		'Cookiebot'          => array( 'cookiebot', 'cookiebot' ),
		'Termly'             => array( 'uk-cookie-consent', 'termly' ),
		'iubenda'            => array( 'iubenda-cookie-law-solution', 'iubenda' ),
		'Real Cookie Banner' => array( 'real-cookie-banner', 'rcb' ),
		'Borlabs Cookie'     => array( 'borlabs-cookie', 'BorlabsCookie' ),
		'GDPR Framework'     => array( 'gdpr-framework', 'gdpr_' ),
		'EU Cookie Law'      => array( 'eu-cookie-law', 'peadig_eucookie' ),
		'WF Cookie Consent'  => array( 'wf-cookie-consent', 'wf_cookieconsent' ),
	);
	$plugins = get_plugins();
	$out     = array();
	foreach ( $known as $label => list( $slug, $prefix ) ) {
		$file = '';
		foreach ( array_keys( $plugins ) as $f ) {
			if ( str_starts_with( $f, $slug . '/' ) ) {
				$file = $f;
				break;
			}
		}
		$names = $wpdb->get_col( $wpdb->prepare(
			"SELECT option_name FROM {$wpdb->options} WHERE option_name LIKE %s AND option_name NOT LIKE %s",
			$wpdb->esc_like( $prefix ) . '%',
			'%transient%'
		) );
		if ( ! $file && ! $names ) {
			continue;
		}
		$out[ $label ] = array(
			'installed'    => (bool) $file,
			'active'       => $file && is_plugin_active( $file ),
			'option_names' => $names,
		);
	}
	return $out;
}

/** Keys ("priority|index") of the callbacks now on the shutdown hook. */
function tracker_audit_probe_shutdown_keys(): array {
	global $wp_filter;
	$keys = array();
	if ( ! empty( $wp_filter['shutdown'] ) ) {
		foreach ( $wp_filter['shutdown']->callbacks as $priority => $callbacks ) {
			foreach ( array_keys( $callbacks ) as $idx ) {
				$keys[ $priority . '|' . $idx ] = true;
			}
		}
	}
	return $keys;
}

/**
 * Remove shutdown callbacks added since $before was taken, so deferred writes
 * cannot run after the rollback. Returns "owner name" for each one removed.
 */
function tracker_audit_probe_remove_new_shutdown( array $before ): array {
	global $wp_filter;
	$removed = array();
	if ( empty( $wp_filter['shutdown'] ) ) {
		return $removed;
	}
	foreach ( $wp_filter['shutdown']->callbacks as $priority => $callbacks ) {
		foreach ( $callbacks as $idx => $cb ) {
			if ( isset( $before[ $priority . '|' . $idx ] ) ) {
				continue;
			}
			$d = tracker_audit_probe_describe( $cb['function'] );
			remove_action( 'shutdown', $cb['function'], $priority );
			$removed[] = $d['owner'] . ' ' . $d['name'];
		}
	}
	return $removed;
}

/** Tables with this site's prefix that a ROLLBACK cannot undo (not InnoDB). */
function tracker_audit_probe_non_innodb_tables(): array {
	global $wpdb;
	return array_values( (array) $wpdb->get_col( $wpdb->prepare(
		"SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE' AND TABLE_NAME LIKE %s AND ( ENGINE IS NULL OR ENGINE <> 'InnoDB' )",
		$wpdb->esc_like( $wpdb->prefix ) . '%'
	) ) );
}

function tracker_audit_probe_inventory() {
	// Keep this response out of page caches and proxies, before any other code runs.
	nocache_headers();
	if ( ! defined( 'DONOTCACHEPAGE' ) ) {
		define( 'DONOTCACHEPAGE', true );
	}
	if ( tracker_audit_probe_expired() ) {
		return new WP_Error( 'tracker_audit_expired', 'This probe expired. Delete the file.', array( 'status' => 410 ) );
	}
	if ( ! function_exists( 'get_plugins' ) ) {
		require_once ABSPATH . 'wp-admin/includes/plugin.php';
	}
	$theme   = wp_get_theme();
	$all     = get_plugins();
	$plugins = array();
	foreach ( (array) get_option( 'active_plugins', array() ) as $file ) {
		$plugins[] = array(
			'file'    => $file,
			'name'    => $all[ $file ]['Name'] ?? '',
			'version' => $all[ $file ]['Version'] ?? '',
		);
	}
	$options    = tracker_audit_probe_options();
	$consent    = tracker_audit_probe_consent();
	$non_innodb = tracker_audit_probe_non_innodb_tables();
	$db_dropin  = file_exists( WP_CONTENT_DIR . '/db.php' );

	// Other plugins' code can write to the database (view counters, stats logs), even
	// on set_current_user. Run all of it inside a transaction and roll back, so no rows
	// stay behind. If the transaction cannot start, run nothing.
	// If a callback exits, the connection closes and MySQL rolls back on its own.
	// The limits text in the response lists what a rollback cannot undo.
	global $wpdb;
	if ( false === $wpdb->query( 'START TRANSACTION' ) ) {
		return new WP_Error( 'tracker_audit_no_transaction', 'Could not start a database transaction, so no plugin code was run.', array( 'status' => 500 ) );
	}
	$shutdown_before = tracker_audit_probe_shutdown_keys();
	$removed         = array();
	$hooks           = array();
	try {
		// Render as an anonymous visitor: no admin bar, no admin name, the markup visitors get.
		wp_set_current_user( 0 );
		foreach ( array( 'wp_enqueue_scripts', 'wp_head', 'wp_body_open', 'wp_footer' ) as $hook ) {
			$hooks[ $hook ] = tracker_audit_probe_run_hook( $hook );
		}
	} finally {
		$removed = tracker_audit_probe_remove_new_shutdown( $shutdown_before );
		$wpdb->query( 'ROLLBACK' );
	}

	$response = new WP_REST_Response( array(
		'probe'                      => array(
			'version'          => TRACKER_AUDIT_PROBE_VERSION,
			'expires_in_hours' => (int) max( 0, TRACKER_AUDIT_PROBE_HOURS - tracker_audit_probe_age_hours() ),
		),
		'site'                       => array(
			'home'      => home_url(),
			'wordpress' => get_bloginfo( 'version' ),
			'php'       => PHP_VERSION,
			'theme'     => array(
				'slug'    => get_stylesheet(),
				'name'    => $theme->get( 'Name' ),
				'version' => $theme->get( 'Version' ),
				'parent'  => $theme->parent() ? $theme->parent()->get_stylesheet() : null,
			),
		),
		'plugins'                    => $plugins,
		'mu_plugins'                 => array_keys( get_mu_plugins() ),
		'hooks'                      => $hooks,
		'options'                    => $options,
		'consent_plugins'            => $consent,
		'removed_shutdown_callbacks' => $removed,
		'non_innodb_tables'          => $non_innodb,
		'db_dropin'                  => $db_dropin,
		'limits'                     => 'Collected during a REST request, not a page view. Anything a plugin adds only on certain pages may be missing. The browser audit shows what visitors get. Database writes made by the hook code were rolled back, with these exceptions: writes to the tables in non_innodb_tables, DDL statements (they commit on their own), code that commits its own transaction, persistent object caches, and any database layer that db_dropin points to. Shutdown callbacks the hook code added were removed without running and are listed in removed_shutdown_callbacks; PHP shutdown functions registered outside WordPress hooks cannot be removed. File writes and outbound requests by that code were not undone. A plugin that cached the administrator\'s data at init, before the probe switched to an anonymous visitor, may still print it in an excerpt.',
	) );
	$response->header( 'Cache-Control', 'no-store' );
	return $response;
}
