<?php
namespace ProofportPhpDemo;

function total($items) {
    foreach ($items as $item) if ($item < 0) throw new \DomainException('negative item');
    return array_sum($items);
}
function quotient($a, $b) { return $a / $b; }
function labeled($text) { echo 'label:' . $text; return strtoupper($text); }
function binary_label() { return "\xff\x00"; }
function runtime_failure() { throw new \Error('controlled runtime error'); }
function warning_example() { trigger_error('controlled warning', E_USER_WARNING); return false; }
