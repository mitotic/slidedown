<!--slidoc-defaults --pace=1 -->
# audio+delay plugin example

PluginDef: audioPace = {
init: function(start,end){
    console.log('audioPace.init:', this.pluginId, start, end);
	this.start = start;
    this.end = end;
    this.audioElement = document.getElementById(this.pluginId+'-audio');
    // Pre-load audio file
    this.audioElement.src = this.audioElement.dataset.src+'#t='+this.start+','+this.end;
},

enterSlide: function(paceStart){
    console.log('audioPace.enterSlide:', this.pluginId, paceStart, this.end - this.start);
	if (!paceStart)
	    return null;
	var delaySec = this.end - this.start;
	var audioElem = this.audioElement;
	function hideElem(hide) { audioElem.style.display = hide ? 'none' : null; }
    this.audioElement.addEventListener('loadeddata', function() {
	    setTimeout(hideElem, delaySec*1000.);
        hideElem(true);
	    audioElem.play();
	});
    this.audioElement.src = this.audioElement.dataset.src+'#t='+this.start+','+this.end;
	return delaySec;
},

leaveSlide: function(){
    console.log('audioPace.leaveSlide:', this.pluginId);
},

buttonClick: function(){
    console.log('audioPace.buttonClick:', this.pluginId);
	var html = '<b>Audio Plugin</b>';
	Slidoc.showPopup(html);
}

}

/* PluginHead:

PluginButton: &#x260A;

PluginBody:
<audio id="%(pluginId)s-audio" data-src="wheel.mp3" controls>
<p>Your browser does not support the <code>audio</code> element.</p>
</audio>

*/

PluginEndDef: audioPace

=audioPace.init(0,4) 

---

## Next slide

=audioPace.init(4,8) 

---

## Last slide