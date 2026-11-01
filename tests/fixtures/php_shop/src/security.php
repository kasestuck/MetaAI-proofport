<?php
namespace ProofportPhpDemo;

// This connection is a string-returning test double, never a live database.
class DemoConnection { public function query($sql) { return $sql; } }
function unsafe_query($input) { $db = new DemoConnection(); return $db->query('SELECT name FROM demo WHERE id=' . $input); }
function unsafe_html($value) { echo $value; return null; }
function unsafe_command($command) { return shell_exec($command); }
function unsafe_decode($payload) { return unserialize($payload); }
function unsafe_read($relative) { return file_get_contents(__DIR__ . '/../data/' . $relative); }
function demo_secret() { $demo_secret = 'fixture-placeholder-not-a-real-secret'; return strlen($demo_secret); }
function weak_password($password) { return md5($password); }
function unsafe_upload($source, $destination) { return move_uploaded_file($source, $destination); }
