<?php
/**
 * Plugin Name: Fixture Tracker
 * Description: Test fixture for tracker-audit-probe. Prints and enqueues fake trackers.
 */
add_action( 'wp_head', function () {
	echo "<script async src=\"//www.googletagmanager.com/gtag/js?id=G-FIXTURE123\"></script>\n";
}, 5 );
add_action( 'wp_enqueue_scripts', function () {
	wp_enqueue_script( 'fixture-pixel', 'https://pixel.example.net/p.js', array(), '1', true );
} );
// A closure that exits, at a priority before the callback below: the probe's
// X-Tracker-Audit-Current header must name it as a closure owned by this plugin.
add_action( 'wp_footer', function () {
	if ( get_option( 'fixture_closure_exit' ) ) {
		echo 'closure-partial';
		exit;
	}
}, 5 );
add_action( 'wp_footer', function () {
	if ( get_option( 'fixture_exit' ) ) {
		echo 'partial';
		exit;
	}
	// Write only during the probe's REST request, so stray page views never commit it.
	if ( defined( 'REST_REQUEST' ) && REST_REQUEST ) {
		update_option( 'fixture_write_test', time() ); // the probe must roll this back
		echo '<script>/*fixture-wrote*/</script>'; // lets the check see the write ran in this request
		// A deferred write: the probe must remove this shutdown callback before it can run.
		add_action( 'shutdown', function () {
			update_option( 'fixture_shutdown_write', time() );
		} );
	}
} );
