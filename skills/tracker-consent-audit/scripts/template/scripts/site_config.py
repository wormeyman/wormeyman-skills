"""Everything the scripts need to know about the site under test.

new_audit.py fills in the values in double underscores. Edit the rest by hand
for each site: pick real pages, the form fields a visitor can type into, and
the trackers the site adds itself (not the ad network's).
"""

SITE = "__SITE__"
SITE_HOST = "__SITE_HOST__"  # without www., so subdomains match too
AD_NETWORK = "__AD_NETWORK__"  # Raptive or Mediavine

# Six page types. Replace the post, category and contact paths with real ones.
PAGES = {
    "home": "/",
    "post": "/a-recent-recipe-post/",
    "category": "/category/recipes/",
    "search": "/?s=soup",
    "contact": "/contact/",
    "privacy": "/privacy-policy/",
}

# Pages where audit.py types the canary into a sign-up field (never submitted).
FORM_PAGES = ("home", "contact")
# Sign-up email fields only: comment forms and privacy-request forms prove
# nothing about the newsletter tool.
SIGNUP_EMAIL = ("form:not(#commentform) input[type=email], [data-ff-el] input[type=email], "
                ".formkit-form input[name=email_address]")

# Fields form_test.py types the canary into on the post page, never submitting.
# The first selector is the one the test waits for. If the newsletter form is
# dead (it happens), the comment form is where visitors actually type.
FORM_TEST_FIELDS = ("#commentform input[type=email]", "#commentform textarea#comment")

# Upload endpoints of session recorders. form_test.py waits for one of these
# after the typing, because "canary not found" means nothing without an upload.
RECORDER_UPLOADS = ("clarity.ms/collect", "hotjar.com/api", "hotjar.io", "fullstory.com/rec",
                    "logrocket.io/i", "mouseflow.com", "smartlook.cloud/rec", "luckyorange.com")

CANARY = "__CANARY__"

# Trackers the site adds itself, by registrable domain: (vendor, who adds it).
# Leave "who adds it" as "unknown" until the probe inventory (Task 6) fills it.
SITE_VENDORS = {
    "clarity.ms": ("Microsoft Clarity (session recording)", "unknown"),
    "bing.com": ("Microsoft Clarity / Bing", "unknown"),
    "google-analytics.com": ("Google Analytics 4", "unknown"),
    "googletagmanager.com": ("Google Analytics 4 (gtag loader)", "unknown"),
    "facebook.com": ("Meta Pixel", "unknown"),
    "facebook.net": ("Meta Pixel", "unknown"),
    "flodesk.com": ("Flodesk", "unknown"),
    "convertkit.com": ("Kit (ConvertKit)", "unknown"),
    "kit.com": ("Kit (ConvertKit)", "unknown"),
    "pinterest.com": ("Pinterest", "unknown"),
    "pinimg.com": ("Pinterest", "unknown"),
    "wp.com": ("Jetpack / WordPress.com", "unknown"),
    "gaug.es": ("Gauges (added by Pressable hosting)", "unknown"),
    "stay22.com": ("Stay22", "unknown"),
    "gravatar.com": ("Gravatar", "unknown"),
}
