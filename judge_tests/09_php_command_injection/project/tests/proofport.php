<?php
require_once __DIR__ . '/../src/commands.php';
return array('constant_output' => function() {
    if (\ProofportPhpDemo\constant_banner() !== 'proofport-safe') throw new \RuntimeException('constant output changed');
});
