// JS include file for Google services
// Before including this script, define CLIENT_ID, API_KEY, LOGIN_BUTTON_ID, AUTH_CALLBACK and
//   function onGoogleAPILoad() { GService.onGoogleAPILoad(); }
// After this script, include script with src="https://apis.google.com/js/client.js?onload=onGoogleAPILoad"

var TRUNCATE_DIGEST = 8;
var MAXSCORE_ID = '_max_score';

function gen_hmac_token(key, message) {
    // Generates token using HMAC key
    return btoa(md5(message, key, true)).slice(0,TRUNCATE_DIGEST);
}

function gen_user_token(key, user_id) {
    // Generates user token using HMAC key
    return gen_hmac_token(key, 'id:'+user_id);
}

function gen_admin_token(key, user_id) {
    // Generates user token using HMAC key
    return gen_hmac_token(key, 'admin:'+user_id);
}

function gen_late_token(key, user_id, session_name, date_str) {
    // Use UTC date string of the form '1995-12-17T03:24' (append Z for UTC time)
    var date = new Date(date_str);
    if (date_str.slice(-1) != 'Z') {  // Convert local time to UTC
	date.setTime( date.getTime() + date.getTimezoneOffset()*60*1000 );
	date_str = date.toISOString().slice(0,16)+'Z';
    }
    return date_str+':'+gen_hmac_token(key, 'late:'+user_id+':'+session_name+':'+date_str);
}

var GService = {};

function GServiceJSONP(callback_index, json_text) {
    GService.handleJSONP(callback_index, json_text);
}

(function (GService) {
// http://railsrescue.com/blog/2015-05-28-step-by-step-setup-to-send-form-data-to-google-sheets/

var jsonpCounter = 0;
var jsonpReceived = 0;
var jsonpRequests = {};

function requestJSONP(url, queryStr, callback) {
    var suffix = '&prefix=GServiceJSONP';
    if (callback) {
	jsonpCounter += 1;
	jsonpRequests[jsonpCounter] = [callback, url];
	suffix += '&callback='+jsonpCounter;
    }

    url += '?'+queryStr+suffix;
    Slidoc.log('requestJSONP:', url);

    var head = document.head;
    var script = document.createElement("script");

    script.setAttribute("src", url);
    head.appendChild(script);
    head.removeChild(script);
}

GService.handleJSONP = function(callback_index, json_obj) {
    Slidoc.log('GService.handleJSONP:', callback_index);
    if (!callback_index)
	return;
    if (!(callback_index in jsonpRequests)) {
	Slidoc.log('GService.handleJSONP: Error - Invalid JSONP callback index: '+callback_index);
	return;
    }
    var outOfSequence = (callback_index != jsonpReceived+1);
    jsonpReceived = Math.max(callback_index, jsonpReceived);
    var callback = jsonpRequests[callback_index][0];
    delete jsonpRequests[callback_index];
    if (callback)
	callback(json_obj || null, '', outOfSequence);
}
    
function handleCallback(responseText, callback, outOfSequence){
    if (!callback)
	return;
    var obj = null;
    var msg = '';
    try {
        obj = JSON.parse(responseText)
    } catch (err) {
        Slidoc.log('JSON parsing error:', err, responseText);
        msg = 'JSON parsing error';
    }
    callback(obj, msg, outOfSequence);
}

var sendDataCounter = 0;
var receiveDataCounter = 0;

GService.sendData = function (data, url, callback, useJSONP) {
  /// callback(result_obj, optional_err_msg)

  var XHR = new XMLHttpRequest();
  var urlEncodedData = "";
  var urlEncodedDataPairs = [];

  sendDataCounter += 1;
  var currentDataCounter = sendDataCounter;
  XHR.onreadystatechange = function () {
      var DONE = 4; // readyState 4 means the request is done.
      var OK = 200; // status 200 is a successful return.
      if (XHR.readyState === DONE) {
	var outOfSequence = (currentDataCounter != receiveDataCounter+1);
        receiveDataCounter = Math.max(currentDataCounter, receiveDataCounter);
        if (XHR.status === OK) {
          Slidoc.log('XHR: '+XHR.status, XHR.responseText);
	  handleCallback(XHR.responseText, callback, outOfSequence);
        } else {
          Slidoc.log('XHR Error: '+XHR.status, XHR.responseText);
          if (callback)
              callback(null, 'Error in HTTP request', outOfSequence)
        }
      }
  };

  // Encoded key=value pairs
    for (var name in data) {
    urlEncodedDataPairs.push(encodeURIComponent(name) + '=' + encodeURIComponent(data[name]));
  }
  // Replaces encoded spaces with plus symbol to mimic form behavior
  urlEncodedData = urlEncodedDataPairs.join('&').replace(/%20/g, '+');

  if (useJSONP) {
      requestJSONP(url, urlEncodedData, callback);
      return;
  }

  // We setup our request
  XHR.open('POST', url);

  // We add the required HTTP header to handle a form data POST request
  XHR.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
  XHR.setRequestHeader('Content-Length', urlEncodedData.length);
  Slidoc.log('sendData:', urlEncodedData, url, useJSONP);
  // And finally, We send our data.
  XHR.send(urlEncodedData);
}

function GoogleProfile(clientId, apiKey, loginButtonId, authCallback) {
    //Include script src="https://apis.google.com/js/client.js?onload=handleClientLoad"
    // authCallback(this.auth)
    this.clientId = clientId;
    this.apiKey = apiKey;
    this.loginButtonId = loginButtonId;
    this.authCallback = authCallback || null;
    this.scopes = 'https://www.googleapis.com/auth/userinfo.email';
    this.auth = null;
}

GoogleProfile.prototype.onLoad = function () {
    Slidoc.log('GoogleProfile.onLoad:');
    gapi.client.setApiKey(this.apiKey);
    window.setTimeout(this.requestAuth.bind(this, true), 5);
}


GoogleProfile.prototype.requestAuth = function (immediate) {
    Slidoc.log('GoogleProfile.requestAuth:');
    gapi.auth.authorize({client_id: this.clientId, scope: this.scopes, immediate: immediate},
                        this.onAuth.bind(this));
    return false;
}

GoogleProfile.prototype.onAuth = function (result) {
    Slidoc.log('GoogleProfile.onAuth:', result);
    var loginButton = document.getElementById(this.loginButtonId);
    if (!loginButton) {
        alert('No login button');
        return;
    }
    if (result && !result.error) {
        // Authenticated
        loginButton.style.display = 'none';
        gapi.client.load('plus', 'v1', this.requestUserInfo.bind(this));
    } else {
        // Need to authenticate
	loginButton.style.display = 'block';
        loginButton.onclick = this.requestAuth.bind(this, false);
        alert('Please login to proceed');
    }
}

GoogleProfile.prototype.requestUserInfo = function () {
    Slidoc.log('GoogleProfile.requestUserInfo:');
    var req = gapi.client.plus.people.get({userId: 'me'});
    req.execute(this.onUserInfo.bind(this));
}

GoogleProfile.prototype.onUserInfo = function (resp) {
    Slidoc.log('GoogleProfile.onUserInfo:', resp);
    if (!resp.emails) {
	alert('GAuth: ERROR no emails specified');
        return;
    }

    var email = '';
    for (var j=0; j<resp.emails.length; j++) {
        var email = resp.emails[j];
        if (email.type == 'account') {
	    email = email.value.toLowerCase()
            break;
        }
    }
    if (!resp.adminKey && !resp.id && !email) {
	alert('GAuth: ERROR no user id or email specified');
        return;
    }

    this.auth = {};
    this.auth.email = email;
    this.auth.id = resp.id || email;
    this.auth.altid = '';

    var comps = resp.displayName.split(/\s+/);
    var name = (comps.length > 1) ? comps.slice(-1)+', '+comps.slice(0,-1).join(' ') : resp.displayName;

    this.auth.displayName = name || this.auth.id || this.auth.email;
    this.auth.token = resp.token || '';
    this.auth.domain = resp.domain || '';
    this.auth.image = (resp.image && resp.image.url) ? resp.image.url : ''; 
    this.auth.adminKey = resp.adminKey || '';
    this.auth.remember = resp.remember || false;
    this.auth.validated = null;

    if (this.authCallback)
	this.authCallback(this.auth);
}

GoogleProfile.prototype.receiveUserInfo = function (loginUser, loginToken, loginRemember, callback) {
    var adminKey = '';
    if (/admin(\s|$)/.exec(loginUser)) {
	// Login as admin user using HMAC key. To select specific user initially, use "admin username"
	loginUser = loginUser.slice(5).trim();
	adminKey = loginToken;
	loginToken = gen_admin_token(adminKey, 'admin');
    }

    var email = (loginUser.indexOf('@')>0) ? loginUser : '';
    if (callback)
	this.authCallback = callback;
    this.onUserInfo({adminKey: adminKey, id: loginUser, displayName: loginUser, token: loginToken,
			 emails: [{type: 'account', value:email}], remember: !!loginRemember});
}
	
GoogleProfile.prototype.promptUserInfo = function (user, msg, callback) {
    var slidocCookie = Slidoc.getServerCookie();
    if (slidocCookie) {
	var comps = slidocCookie.split(":");
	var cookieUser = comps[0];
	var cookieToken = comps.length > 1 ? comps[1] : '';
	if (user || msg || callback || !cookieUser || !cookieToken) {
	    // Re-do authentication to update cookie
	    var urlPath = location.pathname;
	    if (location.search)
		urlPath += location.search;
	    if (location.hash)
		urlPath += location.hash;
	    var href = "/_auth/login/?next="+encodeURIComponent(urlPath);
	    if (msg)
		href += "&error="+encodeURIComponent(msg);
	    location.href = href;
	    return;
	} else {
	    // Use user/token from cookie
	    this.receiveUserInfo(cookieUser, cookieToken, false, callback);
	    return;
	}
    }
    var loginElem = document.getElementById('gdoc-login-popup');
    var loginOverlay = document.getElementById('gdoc-login-overlay');
    var loginUserElem = document.getElementById('gdoc-login-user');
    var loginTokenElem = document.getElementById('gdoc-login-token');
    var loginRememberElem = document.getElementById('gdoc-login-remember');
    loginUserElem.value = user || '';
    loginRememberElem.checked =  !!GService.gprofile.auth && GService.gprofile.auth.remember;
    document.getElementById('gdoc-login-message').textContent = msg || '';

    var gprofile = this; // Because 'this' is re-bound on callback
    document.getElementById('gdoc-login-button').onclick = function (evt) {
	loginElem.style.display = 'none';
        loginOverlay.style.display = 'none';
	var loginUser = loginUserElem.value.trim().toLowerCase();
	var loginToken = loginTokenElem.value.trim();

	if (!loginUser) {
	    alert('Please provide user name for login');
	    return false;
	}

	if (!loginToken) {
	    alert('Please provide token for login');
	    return false;
	}
	gprofile.receiveUserInfo(loginUser, loginToken, loginRememberElem.checked, callback);
    }
    loginElem.style.display = 'block';
    loginOverlay.style.display = 'block';
    window.scrollTo(0,0);
}

function GoogleSheet(url, sheetName, preHeaders, fields, useJSONP) {
    this.url = url;
    this.sheetName = sheetName;
    this.preHeaders = preHeaders || [];
    this.fields = fields || [];
    this.headers = this.preHeaders.concat(this.fields);
    this.useJSONP = !!useJSONP;
    this.callbackCounter = 0;
    this.pendingUpdates = 0;
    this.userUpdateCounter = {};
    this.columnIndex = {};
    this.timestamps = {};
    this.cacheAll = null;
    this.roster = null;
    for (var j=0; j<this.headers.length; j++)
        this.columnIndex[this.headers[j]] = j;
}

GoogleSheet.prototype.send = function(params, callType, callback) {
    params = JSON.parse(JSON.stringify(params));
    if (!params.id && GService.gprofile.auth.id)
	params.id = GService.gprofile.auth.id;

    if (GService.gprofile.auth.token)
	params.token = GService.gprofile.auth.token;

    if (GService.gprofile.auth.adminKey)
	params.admin = 'admin';
    params.sheet = this.sheetName;

    var userId = params.id||null;

    if (!this.headers.length)
	params.getheaders = 1;

    GService.sendData(params, this.url, this.callback.bind(this, userId, callType, callback),
		      this.useJSONP);
}
    
GoogleSheet.prototype.callback = function (userId, callbackType, outerCallback, result, err_msg, outOfSequence) {
    // outerCallback(obj, {error: err_msg, messages: messages})
    // obj == null on error
    // obj == {} for non-existent row
    // obj == {id: ..., name: ..., } for returned row
    Slidoc.log('GoogleSheet: callback', this.callbackCounter, userId, callbackType, result, err_msg, outOfSequence);
    this.callbackCounter -= 1;

    if (callbackType == 'putRow' || callbackType == 'updateRow') {
	this.pendingUpdates -= 1;
	if (userId && userId in this.userUpdateCounter)
	    this.userUpdateCounter[userId] -= 1;
    }

    if (!result)
        Slidoc.log('GoogleSheet: ERROR in '+callbackType+' callback: '+err_msg);

    if (outerCallback) {
        var retval = null;
	var retStatus = {error: '', info: null, messages: null};
        if (result) {
	    try {
	    if (result.result == 'success' && result.value) {
		if (callbackType != 'getAll') {
		    retval = (result.value.length == 0) ? {} : this.row2obj(result.value, result.headers);
		} else {
		    retval = {};
		    for (var j=0; j<result.value.length; j++) {
			var row = result.value[j];
			if (row.length) {
			    var rowObj = this.row2obj(row);
			    retval[rowObj.id] = rowObj;
			}
		    }
		}

		retStatus.info = result.info || {};
		if (result.headers)
		    retStatus.info.headers = result.headers;

		if (userId) {
		    if (!outOfSequence && retStatus.info.prevTimestamp && this.timestamps[userId] && retStatus.info.prevTimestamp != this.timestamps[userId]) {
			retval = null;
			retStatus.error = 'GoogleSheet: ERROR Timestamp mismatch; expected '+this.timestamps[userId]+' but received '+retStatus.info.prevTimestamp+'. Conflicting modifications from another active browser session?';
		    }
		    if (retStatus.info.timestamp)                 // Update timestamp for user
			this.timestamps[userId] = Math.max(retStatus.info.timestamp, this.timestamps[userId] || 0);
		}

	    } else if (result.result == 'error' && result.error) {
		retStatus.error = err_msg ? err_msg + ';' + result.error : result.error;
	    }

		if (result.messages)
		    retStatus.messages = result.messages.split('\n');
	    } catch(err) {
		retval = null;
		retStatus.error = 'GoogleSheet: ERROR in GoogleSheet.callback: '+err;
		Slidoc.log(retStatus.error);
	    }
	}
	
        outerCallback(retval, retStatus);
    }
}

GoogleSheet.prototype.row2obj = function(row, headers) {
    headers = headers || this.headers;
    if (row.length != headers.length)
	throw('GoogleSheet: row2obj - ERROR Incorrect number of row values received from Google Sheet: expected '+headers.length+' but got '+row.length+' (Enable grade_response feature for extra grading columns?)');

    var obj = {};
    for (var j=0; j<row.length; j++)
        obj[headers[j]] = row[j];
    return obj;
}

GoogleSheet.prototype.obj2row = function(obj) {
    var row = [];
    var keys = Object.keys(obj);
    for (var j=0; j<this.headers.length; j++) {
        row.push(null);
    }
    for (var j=0; j<keys.length; j++) {
       var key = keys[j];
       if (!(key in this.columnIndex))
           throw('GoogleSheet: Invalid column header: '+key);
       row[this.columnIndex[key]] = obj[key];
    }
    return row;
}

GoogleSheet.prototype.createSheet = function (callback) {
    var params = { headers: JSON.stringify(this.headers) };
    this.callbackCounter += 1;
    this.send(params, 'createSheet', callback);
}

GoogleSheet.prototype.putRow = function (rowObj, opts, callback) {
    // opts = {get:, id:, nooverwrite:, submit:}
    // Specify opts.id to override id
    // Specify opts.get to retrieve the existing/overwritten row.
    // Specify opts.nooverwrite to not overwrite any existing row with same id
    // Specify opts.submit to update submitTimestamp
    // opts.get with opts.nooverwrite will return the existing row, or the newly inserted row.
    Slidoc.log('GoogleSheet.putRow:', rowObj, opts);

    if (!rowObj.id || (opts.nooverwrite && !rowObj.name))
        throw('GoogleSheet.putRow: Must provide id and name to put row');

    if (this.cacheAll)
        throw('GoogleSheet.putRow: Cannot putRow when caching');

    var row = this.obj2row(rowObj);
    var params = {row: JSON.stringify(row)};
    if (opts.id)
        params.id = opts.id;
    if (opts.get)
        params.get = '1';
    if (opts.nooverwrite)
        params.nooverwrite = '1';
    if (opts.submit)
        params.submit = '1';

    this.putSend(rowObj.id, params, 'putRow', callback);
}

GoogleSheet.prototype.putSend = function (userId, params, callType, callback) {
    if (!(userId in this.userUpdateCounter))
	this.userUpdateCounter[userId] = 0;
    
    if (!this.userUpdateCounter[userId] && this.timestamps[userId])  // Send timestamp if no pending updates
	params.timestamp = this.timestamps[userId];

    this.userUpdateCounter[userId] += 1;

    this.pendingUpdates += 1;
    this.callbackCounter += 1;
    this.send(params, callType, callback);
}
    
GoogleSheet.prototype.authPutRow = function (rowObj, opts, callback, createSheet, retval, retStatus) {
    // opts = {get:, id:, nooverwrite:, submit:}
    // Fills in id, name etc. from GService.gprofile.auth before calling putRow
    Slidoc.log('GoogleSheet.authPutRow:', opts, !!callback, createSheet, retval, retStatus);
    if (createSheet) {
        // Call authPutRow after creating sheet
        this.createSheet( this.authPutRow.bind(this, rowObj, opts, callback, null) ); // createSheet=null needed to prevent looping
        return;
    } else if (retStatus && retStatus.error) {
	callback(null, retStatus);
	return;
    }

    var extObj = {};
    for (var j=0; j < this.fields.length; j++) {
        var header = this.fields[j];
        if (header in rowObj)
            extObj[header] = rowObj[header]
    }
    var auth = GService.gprofile.auth;
    extObj.id = opts.id || auth.id;
    if (opts.nooverwrite) {
	// Creating/reading row, but not updating it; copy management fields
	extObj.name = auth.displayName || '';
	for (var j=2; j<this.preHeaders.length; j++)
	    extObj[this.preHeaders[j]] = auth[this.preHeaders[j]] || '';
    }
    return this.putRow(extObj, opts, callback, createSheet);
}

GoogleSheet.prototype.updateRow = function (updateObj, opts, callback) {
    // Only works with existing rows
    // Specify get to return updated row
    // opts = {get:}
    Slidoc.log('GoogleSheet.updateRow:', updateObj, opts);
    if (!updateObj.id)
        throw('GoogleSheet.updateRow: Must provide id to update row');

    var cachedRow = null;
    if (this.cacheAll) {
	// Update headers in cached copy
	cachedRow = this.cacheAll[updateObj.id];
	if (!cachedRow)
	    throw("GoogleSheet.updateRow: id '"+updateObj.id+"'not found in cache");
    }

    var updates = [];
    var keys = Object.keys(updateObj);
    for (var j=0; j<keys.length; j++) {
       var key = keys[j];
       if (!(key in this.columnIndex))
           throw('GoogleSheet.updateRow: Invalid column header: '+key);
	updates.push( [key, updateObj[key]] );
	if (cachedRow && key != 'id' && key != 'Timestamp' && key in cachedRow) // Update cached row
	    cachedRow[key] = updateObj[key]
    }

    var params = {id: updateObj.id, update: JSON.stringify(updates)};
    if (opts.get)
        params.get = '1';

    this.putSend(updateObj.id, params, 'updateRow', callback);
}

GoogleSheet.prototype.getRow = function (id, callback) {
    // If !id, GService.gprofile.auth.id is used
    // callback(result, retStatus)
    // result == null on error
    // result == {} for non-existent row
    // result == {id: ..., name: ..., } for returned row
    Slidoc.log('GoogleSheet.getRow:', id, !!callback);

    if (!id) id = GService.gprofile.auth.id;

    if (!id)
        throw('GoogleSheet.getRow: Null id for getRow');
    if (!callback)
        throw('GoogleSheet.getRow: Must specify callback for getRow');

    if (this.cacheAll) {
	if (id in this.cacheAll)
	    callback(this.cacheAll[id], {error: '', messages: ['Info:FROM_CACHE:']});
	else
	    callback(null, {error: "id '"+id+"' not found in cache", messages: []});
	return;
    }

    var params = {id: id, get: '1'};
    this.callbackCounter += 1;
    this.send(params, 'getRow', callback);
}


GoogleSheet.prototype.getAll = function (callback) {
    // callback(result, retStatus)
    // result == null on error
    // result == {} for empty sheet
    // result == {id: {id: ..., name: ..., }} for returned rows
    if (!callback)
        throw('GoogleSheet: Must specify callback for getAll');

    var params = {all: '1', get: '1'};
    this.callbackCounter += 1;
    this.send(params, 'getAll', callback);
}

GoogleSheet.prototype.getRoster = function() {
    return this.roster;
}

GoogleSheet.prototype.initCache = function(allRows) {
    this.cacheAll = allRows;
    var ids = Object.keys(allRows);
    this.roster = [];
    for (var j=0; j<ids.length; j++) {
	if (ids[j] && ids[j] != MAXSCORE_ID) {
	    var rowObj = allRows[ids[j]];
	    if (rowObj.name && rowObj.Timestamp) {
		this.roster.push([rowObj.name, ids[j]]);
		this.timestamps[ids[j]] = (new Date(rowObj.Timestamp)).getTime();
	    }
	}
    }
    this.roster.sort(function(a,b){ if (a[0] != b[0]) {return (a[0] > b[0]) ? 1 : -1} else {return (a[1] > b[1]) ? 1 : -1}});
    Slidoc.log('GoogleSheet.initCache:', this.roster);
}

GService.GoogleSheet = GoogleSheet;

GService.gprofile = new GoogleProfile(CLIENT_ID, API_KEY, LOGIN_BUTTON_ID, AUTH_CALLBACK);

GService.onGoogleAPILoad = function () {
    Slidoc.log('GService.onGoogleAPILoad:');
    GService.gprofile.onLoad();
}

})(GService, CLIENT_ID, API_KEY, LOGIN_BUTTON_ID, AUTH_CALLBACK);
