# Test 2c: BRAM36 count per memory field from a routed checkpoint (the hierarchical utilization report drops some
# state_mem instances in the BRAM runs). Usage: vivado -mode batch -source bram_by_field.tcl -tclargs <dcp> <out>
open_checkpoint [lindex $argv 0]
set f [open [lindex $argv 1] w]
array set n {}
foreach c [get_cells -hier -filter {REF_NAME =~ RAMB36*}] {
  if {[regexp {(g_bank\[[01]\]\.u_m_[a-z0-9_]+|u_m_[a-z0-9_]+)} $c m]} { set k $m } else { set k "other:$c" }
  if {[info exists n($k)]} { incr n($k) } else { set n($k) 1 }
}
foreach k [lsort [array names n]] { puts $f "$k $n($k)" }
close $f
