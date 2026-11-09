Ad3Guard signal path now closes the AD3 before any logging and mutes logging during the close, so a reentrant stdout write cannot skip the device close.
