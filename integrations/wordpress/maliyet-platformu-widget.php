<?php
/**
 * Plugin Name: Maliyet Platformu Widget
 * Description: Embeds the immutable Maliyet Platformu public calculation widget.
 * Version: 1.0.0
 * Requires at least: 6.5
 * Requires PHP: 8.1
 * License: Proprietary
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

const MALIYET_WIDGET_VERSION = '1.2.0';

/**
 * Validate an exact HTTPS origin. Paths, credentials, query strings and fragments are forbidden.
 */
function maliyet_widget_https_origin(string $value): ?string
{
    $value = trim($value);
    if ($value === '') {
        return null;
    }

    $parts = wp_parse_url($value);
    if (!is_array($parts) || ($parts['scheme'] ?? '') !== 'https' || empty($parts['host'])) {
        return null;
    }
    foreach (['user', 'pass', 'query', 'fragment'] as $forbidden) {
        if (isset($parts[$forbidden])) {
            return null;
        }
    }
    if (isset($parts['path']) && $parts['path'] !== '' && $parts['path'] !== '/') {
        return null;
    }

    $host = strtolower((string) $parts['host']);
    $port = isset($parts['port']) ? ':' . (int) $parts['port'] : '';
    return 'https://' . $host . $port;
}

/**
 * Validate the public deployment identifier without accepting arbitrary path material.
 */
function maliyet_widget_deployment_id(string $value): ?string
{
    $value = strtolower(trim($value));
    if (!preg_match(
        '/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/D',
        $value
    )) {
        return null;
    }
    return $value;
}

/**
 * Render [maliyet_widget deployment_id="..." api_base="https://..." cdn_base="https://..."]
 */
function maliyet_widget_shortcode(array $attributes = []): string
{
    static $asset_origin = null;

    $attributes = shortcode_atts(
        [
            'deployment_id' => '',
            'api_base' => '',
            'cdn_base' => '',
        ],
        $attributes,
        'maliyet_widget'
    );

    $deployment_id = maliyet_widget_deployment_id((string) $attributes['deployment_id']);
    $api_base = maliyet_widget_https_origin((string) $attributes['api_base']);
    $cdn_base = maliyet_widget_https_origin((string) $attributes['cdn_base']);
    if ($deployment_id === null || $api_base === null || $cdn_base === null) {
        return '';
    }

    $widget = sprintf(
        '<div data-maliyet-widget data-deployment-id="%s"></div>',
        esc_attr($deployment_id)
    );

    if ($asset_origin !== null) {
        if (!hash_equals($asset_origin['api_base'], $api_base) || !hash_equals($asset_origin['cdn_base'], $cdn_base)) {
            return '';
        }
        return $widget;
    }

    $asset_origin = [
        'api_base' => $api_base,
        'cdn_base' => $cdn_base,
    ];
    $stylesheet = $cdn_base . '/widget/' . MALIYET_WIDGET_VERSION . '/styles.css';
    $loader = $cdn_base . '/widget/' . MALIYET_WIDGET_VERSION . '/loader.js';

    return sprintf(
        '<link rel="stylesheet" href="%s">%s<script src="%s" data-maliyet-api-base="%s" defer></script>',
        esc_url($stylesheet),
        $widget,
        esc_url($loader),
        esc_attr($api_base)
    );
}

add_shortcode('maliyet_widget', 'maliyet_widget_shortcode');
