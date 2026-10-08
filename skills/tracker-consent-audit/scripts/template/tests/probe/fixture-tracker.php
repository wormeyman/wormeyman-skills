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
add_action( 'wp_footer', function () {
	if ( get_option( 'fixture_exit' ) ) {
		echo 'partial';
		exit;
	}
	update_option( 'fixture_write_test', time() ); // the probe must roll this back
} );
