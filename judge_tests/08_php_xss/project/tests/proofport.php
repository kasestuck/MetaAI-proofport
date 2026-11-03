<?php
require_once __DIR__ . '/../src/view.php';
return array('raw_output' => function() {
    ob_start(); $length = \JudgeXss\render('<b>demo</b>'); $text = ob_get_clean();
    if ($text !== '<b>demo</b>' || $length !== 11) throw new \RuntimeException('output contract changed');
});
