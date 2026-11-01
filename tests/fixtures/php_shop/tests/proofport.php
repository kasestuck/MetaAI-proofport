<?php
namespace ProofportPhpDemo;
require_once __DIR__ . '/../src/legacy.php';
require_once __DIR__ . '/../src/math.php';
require_once __DIR__ . '/../src/security.php';
require_once __DIR__ . '/../src/commands.php';

function check($condition) { if (!$condition) throw new \RuntimeException('fixture assertion failed'); }
return array(
    'pair_order' => function() { check(first_pair(array('a' => 3)) === array(1 => 3, 'value' => 3, 0 => 'a', 'key' => 'a')); },
    'pair_empty' => function() { check(first_pair(array()) === false); },
    'character' => function() { check(first_character('safe') === 's'); },
    'sum' => function() { check(total(array(1, 2, 3)) === 6); },
    'division' => function() { check(quotient(5, 2) === 2.5); },
    'exception' => function() { try { total(array(-1)); } catch (\DomainException $e) { return; } throw new \RuntimeException('exception required'); },
    'binary' => function() { check(binary_label() === "\xff\x00"); },
    'password_format' => function() { check(weak_password('demo') === 'fe01ce2a7fbac8fafaed7c982a04e229'); },
    'constant_command' => function() { check(constant_banner() === 'proofport-safe'); }
);
