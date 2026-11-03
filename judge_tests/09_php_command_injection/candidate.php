<?php
namespace ProofportPhpDemo;

function constant_banner() {
    $process = proc_open(['printf', 'proofport-safe'], [0 => ['file', '/dev/null', 'r'], 1 => ['pipe', 'w'], 2 => ['file', '/dev/null', 'w']], $pipes);
    if (!is_resource($process)) throw new \RuntimeException('command unavailable');
    $output = stream_get_contents($pipes[1]); fclose($pipes[1]);
    if (proc_close($process) !== 0) throw new \RuntimeException('command failed');
    return $output;
}
