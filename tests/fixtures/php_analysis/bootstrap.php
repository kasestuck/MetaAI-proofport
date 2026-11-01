<?php
// Original P6.1 inventory fixture. Never execute on the host.
namespace ProofportDemo;
require_once __DIR__ . '/lib/prices.php';

class Basket {
    public function total(array $items) { return array_sum($items); }
}

function legacy_pair(array $items) { return each($items); }
function legacy_offset($text) { return $text{0}; }
function compare_value($value) { return $value == 'demo'; }
