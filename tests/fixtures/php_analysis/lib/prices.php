<?php
namespace ProofportDemo;

function price_total($count, $unit) { return $count * $unit; }

// Fake declarations and removed calls must not appear in lexical inventory:
// class CommentOnly { function fake() { create_function('', ''); } }
$documentation = 'function LiteralOnly() { each([]); }';
$text = <<<'GUIDE'
class HeredocOnly { function hidden() {} }
GUIDE;
