// UI strings. Every visible string goes through t(); English and Georgian.

const en = {
  'app.title': 'Map Studio',
  'lang.en': 'EN',
  'lang.ka': 'ქართული',
  'lang.label': 'Language of the map and the studio',
  'in.en': 'in English',
  'in.ka': 'in Georgian',

  'top.place': 'Place',
  'top.theme': 'Map style',
  'theme.drawn': 'drawn',
  'theme.notDrawn': 'not drawn yet',
  'top.undo': 'Undo',
  'top.redo': 'Redo',
  'top.export': 'Export',
  'top.fonts': 'Fonts',
  'export.pdfPoster': 'PDF, poster size',
  'export.pdfPaper': 'PDF on {paper} paper',
  'export.pdfSize': '{w} × {h} mm, for printing',
  'fonts.tip': 'Change the fonts of this map',
  'fonts.loading': 'Reading the fonts…',
  'fonts.note': 'Choosing a font redraws the map. It is remembered for this place and style.',
  'fonts.noteSite': 'Choosing a font redraws your copy of the map. Others still see the original.',
  'fonts.signIn': 'Sign in to change fonts. Your choice only changes your copy of the map.',
  'fonts.add': 'Add a font file…',
  'fonts.addSub': '.ttf or .otf, copied into the project’s fonts folder',
  'fonts.back': 'Back to the text roles',
  'fonts.themeFont': 'The style’s own font',
  'fonts.yours': 'changed',
  'fonts.mine': 'in project',
  'fonts.added': 'Added {name}. Pick it for any text role.',
  'fonts.failed': 'The font could not be changed: {why}',
  'fonts.role.display': 'Title and place names',
  'fonts.role.text': 'Text, legend and index',
  'fonts.role.italic': 'Italic text: water, notes',
  'fonts.role.caps': 'Landmark labels',
  'fonts.role.hand': 'Handwriting',
  'top.panelHide': 'Hide the side panel',
  'top.panelShow': 'Show the side panel',

  'save.saved': 'Saved',
  'save.saving': 'Saving…',
  'save.dirty': 'Unsaved changes',
  'save.error': 'Couldn’t save',
  'save.retry': 'Try again',
  'save.errorToast': 'Your additions couldn’t be saved. Check that the studio server is still running.',

  'redraw.full': 'Redraw map with my additions',
  'redraw.short': 'Redraw map',
  'redraw.tiny': 'Redraw',
  'redraw.busyTiny': '{n} s',
  'redraw.tipDirty': 'Your latest changes are not on the map yet. Redrawing takes 5 to 40 seconds.',
  'redraw.tipClean': 'The map already shows everything you added.',
  'redraw.busy': 'Drawing… {n} s',
  'redraw.done': 'The map was redrawn with your additions.',
  'redraw.doneNew': 'The map is drawn.',

  'export.png': 'PNG for printing',
  'export.svg': 'SVG, vector',
  'export.size': '{w} × {h} px',
  'export.scalable': 'scales to any size',
  'export.stale': 'These files show the map as it was last drawn. Redraw first to include your latest changes.',
  'export.none': 'Nothing to export until the map is drawn.',

  'tool.select': 'Select and move',
  'tool.place': 'Add a place',
  'tool.path': 'Draw a path',
  'tool.note': 'Add a note',
  'tool.measure': 'Measure a distance',
  'tools.label': 'Tools',

  'zoom.in': 'Zoom in',
  'zoom.out': 'Zoom out',
  'zoom.fit': 'Show the whole map',
  'zoom.actual': 'Actual size, 100%',
  'zoom.label': 'Zoom',
  'stage.label': 'Map. Drag to move, scroll to zoom.',

  'tab.landmarks': 'Landmarks',
  'tab.additions': 'My additions',
  'panel.label': 'Landmarks and additions',

  'lm.empty.title': 'No landmarks on this map yet',
  'lm.empty.body': 'Once the map is drawn with its landmark icons, they are listed here and you can click them on the map.',
  'lm.startPath': 'Start a path here',
  'lm.elevation': '{n} m above sea level',
  'lm.close': 'Close',

  'add.empty.title': 'Nothing added yet',
  'add.empty.body': 'Mark your own places, draw a path or leave a note. Everything is saved here and drawn into the map when you redraw it.',
  'add.empty.place': 'Add a place',
  'add.empty.path': 'Draw a path',
  'add.empty.note': 'Add a note',
  'add.locate': 'Show on the map',
  'add.delete': 'Delete',
  'add.deleted': '“{name}” was deleted.',
  'add.undo': 'Undo',
  'add.onMap': 'Drawn into the map',
  'add.pending': 'Not on the map yet. Redraw the map to include it.',
  'add.showAll': 'Show all my additions on top of the map',
  'add.showAllHint': 'Additions already drawn into the map are normally not drawn a second time.',

  'field.name': 'Name',
  'field.note': 'Note',
  'field.optional': 'optional',
  'field.icon': 'Icon',
  'field.kind': 'Kind',
  'field.text': 'Text',
  'ph.place': 'e.g. Grandma’s house',
  'ph.placeNote': 'e.g. The gate is always open',
  'ph.path': 'e.g. Walk to the ice cave',
  'ph.note': 'e.g. Best light at sunset',

  'kind.trail': 'Trail',
  'kind.road': 'Road',
  'kind.route': 'Route',

  'icon.none': 'Simple marker',
  'icon.library': 'General',
  'icon.landmarks': 'From this map',
  'icon.empty': 'No icons have been drawn yet. Places get a simple marker for now.',

  'unnamed.place': 'Unnamed place',
  'unnamed.trail': 'Unnamed trail',
  'unnamed.road': 'Unnamed road',
  'unnamed.route': 'Unnamed route',
  'unnamed.note': 'Empty note',

  'stat.length': 'Length',
  'stat.ascent': 'Ascent',
  'stat.descent': 'Descent',
  'stat.time': 'Walking time',
  'stat.lowest': 'Lowest point',
  'stat.highest': 'Highest point',
  'stat.method.tobler': 'Walking time is estimated with Tobler’s hiking function, without breaks.',
  'stat.method.naismith': 'Walking time is estimated with Naismith’s rule, without breaks.',
  'stat.noDem': 'No elevation data for this place, so only the length is shown.',
  'stat.points': '{n} points',
  'profile.label': 'Elevation along the path',
  'profile.at': '{d} · {e}',
  'path.editHint': 'Drag the points on the map to adjust. Click the line to add a point; select a point and press Delete to remove it.',

  'hud.path.start': 'Click the map to start the path',
  'hud.path.second': 'Click to add the next point',
  'hud.path.keys': 'Enter finishes · Backspace removes the last point',
  'hud.finish': 'Finish',
  'hud.cancel': 'Cancel',
  'hud.place': 'Click the map where the place is',
  'hud.note': 'Click the map where the note belongs',
  'hud.measure.start': 'Click two or more points to measure',
  'hud.measure.total': 'Distance',
  'hud.clear': 'Clear',
  'hud.outside': 'Additions can only go inside the map frame.',

  'unit.m': 'm',
  'unit.km': 'km',
  'unit.min': 'min',
  'unit.h': 'h',

  'state.loading': 'Opening the studio…',
  'state.loadingArt': 'Unrolling the map…',
  'state.unreachable.title': 'The studio server isn’t answering',
  'state.unreachable.body': 'Start it from the project folder, then try again:',
  'state.retry': 'Try again',
  'state.noPlaces.title': 'No places to show yet',
  'state.noPlaces.body': 'Fetch a place first, then reload the studio:',
  'state.noThemes.title': 'No map styles found',
  'state.noThemes.body': 'The styles folder has no style to draw with.',
  'state.notDrawn.title': '“{theme}” hasn’t been drawn {inLang} yet',
  'state.notDrawn.body': 'Drawing it takes 5 to 40 seconds. Your places, paths and notes are included.',
  'state.notDrawn.action': 'Draw the map',
  'state.rendering.title': 'Drawing the map…',
  'state.rendering.body': '“{theme}”, {inLang}. This usually takes 5 to 40 seconds.',
  'state.rendering.elapsed': '{n} s',
  'state.failed.title': 'The map couldn’t be drawn',
  'state.failed.body': 'The renderer stopped with an error. The last lines of its log:',
  'state.failed.noLog': 'The renderer gave no details.',
  'state.failed.keep': 'The map on screen is still the previous drawing.',
  'state.failed.dismiss': 'Dismiss',
  'state.imageFailed': 'The map image couldn’t be loaded.',

  'key.del': 'Delete',
};

const ka = {
  'app.title': 'რუკის სტუდია',
  'lang.en': 'EN',
  'lang.ka': 'ქართული',
  'lang.label': 'რუკისა და სტუდიის ენა',
  'in.en': 'ინგლისურად',
  'in.ka': 'ქართულად',

  'top.place': 'ადგილი',
  'top.theme': 'რუკის სტილი',
  'theme.drawn': 'დახატულია',
  'theme.notDrawn': 'ჯერ არ დახატულა',
  'top.undo': 'დაბრუნება',
  'top.redo': 'გამეორება',
  'top.export': 'ექსპორტი',
  'top.fonts': 'შრიფტები',
  'export.pdfPoster': 'PDF, პლაკატის ზომა',
  'export.pdfPaper': 'PDF, {paper} ფურცელზე',
  'export.pdfSize': '{w} × {h} მმ, საბეჭდად',
  'fonts.tip': 'ამ რუკის შრიფტების შეცვლა',
  'fonts.loading': 'შრიფტები იკითხება…',
  'fonts.note': 'შრიფტის არჩევის შემდეგ რუკა თავიდან დაიხატება. არჩევანი ამ ადგილისა და სტილისთვის დამახსოვრდება.',
  'fonts.noteSite': 'შრიფტის არჩევის შემდეგ თქვენი ასლი თავიდან დაიხატება. სხვები ორიგინალს დაინახავენ.',
  'fonts.signIn': 'შრიფტის შესაცვლელად შედით სისტემაში. არჩევანი მხოლოდ თქვენს ასლს შეცვლის.',
  'fonts.add': 'შრიფტის ფაილის დამატება…',
  'fonts.addSub': '.ttf ან .otf — დაკოპირდება პროექტის fonts საქაღალდეში',
  'fonts.back': 'უკან, ტექსტის სახეობებზე',
  'fonts.themeFont': 'სტილის საკუთარი შრიფტი',
  'fonts.yours': 'შეცვლილია',
  'fonts.mine': 'პროექტში',
  'fonts.added': 'დაემატა {name}. აირჩიეთ ნებისმიერი ტექსტისთვის.',
  'fonts.failed': 'შრიფტი ვერ შეიცვალა: {why}',
  'fonts.role.display': 'სათაური და ადგილების სახელები',
  'fonts.role.text': 'ტექსტი, პირობითი ნიშნები, სია',
  'fonts.role.italic': 'დახრილი ტექსტი: წყალი, მინაწერები',
  'fonts.role.caps': 'ღირსშესანიშნაობების წარწერები',
  'fonts.role.hand': 'ხელნაწერი',
  'top.panelHide': 'გვერდითი პანელის დამალვა',
  'top.panelShow': 'გვერდითი პანელის ჩვენება',

  'save.saved': 'შენახულია',
  'save.saving': 'ინახება…',
  'save.dirty': 'შეუნახავი ცვლილებები',
  'save.error': 'შენახვა ვერ მოხერხდა',
  'save.retry': 'ხელახლა ცდა',
  'save.errorToast': 'თქვენი დამატებების შენახვა ვერ მოხერხდა. შეამოწმეთ, ისევ გაშვებულია თუ არა სტუდიის სერვერი.',

  'redraw.full': 'რუკის თავიდან დახატვა ჩემი დამატებებით',
  'redraw.short': 'რუკის თავიდან დახატვა',
  'redraw.tiny': 'თავიდან დახატვა',
  'redraw.busyTiny': '{n} წმ',
  'redraw.tipDirty': 'ბოლო ცვლილებები რუკაზე ჯერ არ ასახულა. თავიდან დახატვას 5–40 წამი სჭირდება.',
  'redraw.tipClean': 'რუკაზე უკვე ასახულია ყველაფერი, რაც დაამატეთ.',
  'redraw.busy': 'იხატება… {n} წმ',
  'redraw.done': 'რუკა თავიდან დაიხატა თქვენი დამატებებით.',
  'redraw.doneNew': 'რუკა დახატულია.',

  'export.png': 'PNG ბეჭდვისთვის',
  'export.svg': 'SVG, ვექტორული',
  'export.size': '{w} × {h} პიქსელი',
  'export.scalable': 'ხარისხს ნებისმიერ ზომაზე ინარჩუნებს',
  'export.stale': 'ამ ფაილებში რუკა ისეთია, როგორიც ბოლოს დაიხატა. ბოლო ცვლილებების ჩასართავად ჯერ რუკა თავიდან დახატეთ.',
  'export.none': 'ექსპორტი შესაძლებელი იქნება რუკის დახატვის შემდეგ.',

  'tool.select': 'მონიშვნა და გადაადგილება',
  'tool.place': 'ადგილის დამატება',
  'tool.path': 'ბილიკის დახატვა',
  'tool.note': 'მინაწერის დამატება',
  'tool.measure': 'მანძილის გაზომვა',
  'tools.label': 'ხელსაწყოები',

  'zoom.in': 'გადიდება',
  'zoom.out': 'დაპატარავება',
  'zoom.fit': 'მთლიანი რუკის ჩვენება',
  'zoom.actual': 'ნამდვილი ზომა, 100%',
  'zoom.label': 'მასშტაბი',
  'stage.label': 'რუკა. გადასაადგილებლად გადაათრიეთ, მასშტაბის შესაცვლელად დაატრიალეთ გორგოლაჭი.',

  'tab.landmarks': 'ღირსშესანიშნაობები',
  'tab.additions': 'ჩემი დამატებები',
  'panel.label': 'ღირსშესანიშნაობები და დამატებები',

  'lm.empty.title': 'ამ რუკაზე ღირსშესანიშნაობები ჯერ არ არის',
  'lm.empty.body': 'როცა რუკა ღირსშესანიშნაობების ნიშნებით დაიხატება, ისინი აქ გამოჩნდება და რუკაზეც შეძლებთ მათზე დაწკაპუნებას.',
  'lm.startPath': 'ბილიკის დაწყება აქედან',
  'lm.elevation': 'ზღვის დონიდან {n} მ',
  'lm.close': 'დახურვა',

  'add.empty.title': 'ჯერ არაფერი დაგიმატებიათ',
  'add.empty.body': 'მონიშნეთ თქვენი ადგილები, დახატეთ ბილიკი ან დატოვეთ მინაწერი. ყველაფერი აქ ინახება და რუკის თავიდან დახატვისას მასზე აისახება.',
  'add.empty.place': 'ადგილის დამატება',
  'add.empty.path': 'ბილიკის დახატვა',
  'add.empty.note': 'მინაწერის დამატება',
  'add.locate': 'რუკაზე ჩვენება',
  'add.delete': 'წაშლა',
  'add.deleted': '„{name}“ წაიშალა.',
  'add.undo': 'დაბრუნება',
  'add.onMap': 'რუკაზე დახატულია',
  'add.pending': 'რუკაზე ჯერ არ არის. დასამატებლად რუკა თავიდან დახატეთ.',
  'add.showAll': 'ყველა ჩემი დამატების ჩვენება რუკის ზემოდან',
  'add.showAllHint': 'რაც რუკაზე უკვე დახატულია, ჩვეულებრივ მეორედ აღარ იხატება.',

  'field.name': 'სახელი',
  'field.note': 'შენიშვნა',
  'field.optional': 'არასავალდებულო',
  'field.icon': 'ნიშანი',
  'field.kind': 'ტიპი',
  'field.text': 'ტექსტი',
  'ph.place': 'მაგ. ბებოს სახლი',
  'ph.placeNote': 'მაგ. ჭიშკარი მუდამ ღიაა',
  'ph.path': 'მაგ. გზა ყინულის მღვიმემდე',
  'ph.note': 'მაგ. მზის ჩასვლისას საუკეთესო ხედია',

  'kind.trail': 'ბილიკი',
  'kind.road': 'გზა',
  'kind.route': 'მარშრუტი',

  'icon.none': 'მარტივი ნიშანი',
  'icon.library': 'ზოგადი',
  'icon.landmarks': 'ამ რუკიდან',
  'icon.empty': 'ნიშნები ჯერ არ დახატულა. ადგილები ამ ეტაპზე მარტივი ნიშნით აღინიშნება.',

  'unnamed.place': 'უსახელო ადგილი',
  'unnamed.trail': 'უსახელო ბილიკი',
  'unnamed.road': 'უსახელო გზა',
  'unnamed.route': 'უსახელო მარშრუტი',
  'unnamed.note': 'ცარიელი მინაწერი',

  'stat.length': 'სიგრძე',
  'stat.ascent': 'აღმართი',
  'stat.descent': 'დაღმართი',
  'stat.time': 'სიარულის დრო',
  'stat.lowest': 'უდაბლესი წერტილი',
  'stat.highest': 'უმაღლესი წერტილი',
  'stat.method.tobler': 'სიარულის დრო მიახლოებითია, გამოთვლილია ტობლერის ფორმულით, შესვენებების გარეშე.',
  'stat.method.naismith': 'სიარულის დრო მიახლოებითია, გამოთვლილია ნეისმითის წესით, შესვენებების გარეშე.',
  'stat.noDem': 'ამ ადგილისთვის სიმაღლის მონაცემები არ არის, ამიტომ მხოლოდ სიგრძეა ნაჩვენები.',
  'stat.points': '{n} წერტილი',
  'profile.label': 'სიმაღლე ბილიკის გასწვრივ',
  'profile.at': '{d} · {e}',
  'path.editHint': 'შესასწორებლად გადაათრიეთ წერტილები რუკაზე. წერტილის დასამატებლად დააწკაპუნეთ ხაზზე; წასაშლელად მონიშნეთ წერტილი და დააჭირეთ Delete-ს.',

  'hud.path.start': 'ბილიკის დასაწყებად დააწკაპუნეთ რუკაზე',
  'hud.path.second': 'დააწკაპუნეთ შემდეგი წერტილის დასამატებლად',
  'hud.path.keys': 'Enter — დასრულება · Backspace — ბოლო წერტილის წაშლა',
  'hud.finish': 'დასრულება',
  'hud.cancel': 'გაუქმება',
  'hud.place': 'დააწკაპუნეთ რუკაზე იქ, სადაც ეს ადგილია',
  'hud.note': 'დააწკაპუნეთ რუკაზე იქ, სადაც მინაწერი უნდა იყოს',
  'hud.measure.start': 'გასაზომად დააწკაპუნეთ ორ ან მეტ წერტილზე',
  'hud.measure.total': 'მანძილი',
  'hud.clear': 'გასუფთავება',
  'hud.outside': 'დამატება მხოლოდ რუკის ჩარჩოს შიგნით შეიძლება.',

  'unit.m': 'მ',
  'unit.km': 'კმ',
  'unit.min': 'წთ',
  'unit.h': 'სთ',

  'state.loading': 'სტუდია იხსნება…',
  'state.loadingArt': 'რუკა იტვირთება…',
  'state.unreachable.title': 'სტუდიის სერვერი არ პასუხობს',
  'state.unreachable.body': 'გაუშვით ის პროექტის საქაღალდიდან და სცადეთ ხელახლა:',
  'state.retry': 'ხელახლა ცდა',
  'state.noPlaces.title': 'საჩვენებელი ადგილები ჯერ არ არის',
  'state.noPlaces.body': 'ჯერ ჩამოტვირთეთ რომელიმე ადგილის მონაცემები და სტუდია თავიდან ჩატვირთეთ:',
  'state.noThemes.title': 'რუკის სტილები ვერ მოიძებნა',
  'state.noThemes.body': 'სტილების საქაღალდეში არცერთი სტილი არ არის.',
  'state.notDrawn.title': '„{theme}“ {inLang} ჯერ არ დახატულა',
  'state.notDrawn.body': 'დახატვას 5–40 წამი სჭირდება. რუკაზე აისახება თქვენი ადგილები, ბილიკები და მინაწერებიც.',
  'state.notDrawn.action': 'რუკის დახატვა',
  'state.rendering.title': 'რუკა იხატება…',
  'state.rendering.body': '„{theme}“, {inLang}. ჩვეულებრივ 5–40 წამი სჭირდება.',
  'state.rendering.elapsed': '{n} წმ',
  'state.failed.title': 'რუკის დახატვა ვერ მოხერხდა',
  'state.failed.body': 'დახატვა შეცდომით შეწყდა. ჟურნალის ბოლო სტრიქონები:',
  'state.failed.noLog': 'დეტალები უცნობია.',
  'state.failed.keep': 'ეკრანზე ისევ ძველი რუკაა.',
  'state.failed.dismiss': 'დახურვა',
  'state.imageFailed': 'რუკის გამოსახულება ვერ ჩაიტვირთა.',

  'key.del': 'Delete',
};

// Georgian labels for generic library icons whose index.json only carries an English label.
const iconKa = {
  house: 'სახლი', home: 'სახლი', tent: 'ბანაკი', camp: 'ბანაკი', campfire: 'კოცონი', fire: 'კოცონი',
  spring: 'წყარო', water: 'წყალი', well: 'ჭა', cave: 'მღვიმე', church: 'ეკლესია', chapel: 'სამლოცველო',
  monastery: 'მონასტერი', tower: 'კოშკი', castle: 'ციხე', fortress: 'ციხესიმაგრე', bridge: 'ხიდი',
  tree: 'ხე', forest: 'ტყე', peak: 'მწვერვალი', mountain: 'მთა', viewpoint: 'გადასახედი', view: 'გადასახედი',
  picnic: 'პიკნიკი', parking: 'ავტოსადგომი', car: 'მანქანა', bus: 'ავტობუსი', shop: 'მაღაზია', cafe: 'კაფე',
  restaurant: 'რესტორანი', food: 'საჭმელი', wine: 'ღვინო', vineyard: 'ვენახი', cellar: 'მარანი',
  school: 'სკოლა', hospital: 'საავადმყოფო', pharmacy: 'აფთიაქი', guesthouse: 'საოჯახო სასტუმრო',
  hotel: 'სასტუმრო', bed: 'ღამისთევა', waterfall: 'ჩანჩქერი', lake: 'ტბა', river: 'მდინარე',
  swim: 'საბანაო', fish: 'თევზაობა', flag: 'დროშა', star: 'ვარსკვლავი', heart: 'გული', pin: 'მარკერი',
  marker: 'მარკერი', camera: 'ფოტო', photo: 'ფოტო', cross: 'ჯვარი', grave: 'სასაფლაო',
  cemetery: 'სასაფლაო', ruin: 'ნანგრევი', ruins: 'ნანგრევები', mill: 'წისქვილი', barn: 'ბოსელი',
  farm: 'ფერმა', field: 'ყანა', garden: 'ბაღი', orchard: 'ხეხილის ბაღი', bench: 'სკამი',
  shelter: 'თავშესაფარი', hut: 'ქოხი', cabin: 'ქოხი', horse: 'ცხენი', cow: 'ძროხა', sheep: 'ცხვარი',
  bee: 'საფუტკრე', beehive: 'საფუტკრე', mushroom: 'სოკო', berry: 'კენკრა', danger: 'საფრთხე',
  info: 'ინფორმაცია', gate: 'ჭიშკარი', monument: 'ძეგლი', statue: 'ქანდაკება', museum: 'მუზეუმი',
  playground: 'სათამაშო მოედანი', stadium: 'სტადიონი', rock: 'კლდე', cliff: 'კლდე', sun: 'მზე',
  sunset: 'მზის ჩასვლა', bike: 'ველოსიპედი', boat: 'ნავი', fuel: 'ბენზინგასამართი', toilet: 'ტუალეტი',
};

const dicts = { en, ka };
let lang = 'en';
const listeners = new Set();

export const getLang = () => lang;
export const uiLang = () => (lang === 'ka' ? 'ka' : 'en');   // UI strings exist in English and Georgian

export function setLang(code) {
  lang = code;
  document.documentElement.lang = uiLang();
  applyI18n(document);
  listeners.forEach((fn) => fn(lang));
}

export const onLang = (fn) => listeners.add(fn);

export function t(key, vars) {
  let s = (dicts[uiLang()] || en)[key] ?? en[key] ?? key;
  if (vars) s = s.replace(/\{(\w+)\}/g, (_, k) => (vars[k] ?? ''));
  return s;
}

// Static markup: data-i18n → text, data-tip → tooltip + aria-label, data-i18n-ph → placeholder, data-i18n-aria → aria-label.
export function applyI18n(root) {
  root.querySelectorAll('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n); });
  root.querySelectorAll('[data-tip]').forEach((el) => { el.setAttribute('aria-label', t(el.dataset.tip)); });
  root.querySelectorAll('[data-i18n-aria]').forEach((el) => { el.setAttribute('aria-label', t(el.dataset.i18nAria)); });
  root.querySelectorAll('[data-i18n-ph]').forEach((el) => { el.setAttribute('placeholder', t(el.dataset.i18nPh)); });
}

/** Name of something that has an English and a local name, in the current language. */
export function localName(obj, key = 'name') {
  if (!obj) return '';
  if (lang === 'en') return obj[key] || obj[`${key}_local`] || '';
  return obj[`${key}_${lang}`] || obj[`${key}_local`] || obj[key] || '';
}

export function iconLabel(item) {
  if (lang === 'en') return item.label || item.id;
  return item[`label_${lang}`] || item.label_local || iconKa[item.id] || item.label || item.id;
}

// Georgian: 1 234,5 (space groups, decimal comma). English: 1,234.5. Done by hand because
// not every browser ships ka-GE number data.
const nf = (digits) => ({
  format(v) {
    const [int, frac] = Math.abs(v).toFixed(digits).split('.');
    const ka = uiLang() === 'ka';
    const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, ka ? '\u00a0' : ',');
    return `${v < 0 ? '−' : ''}${grouped}${frac ? `${ka ? ',' : '.'}${frac}` : ''}`;
  },
});

export function fmtDist(m) {
  if (!Number.isFinite(m)) return '–';
  if (m < 995) return `${nf(0).format(Math.round(m / 5) * 5 || Math.round(m))} ${t('unit.m')}`;
  return `${nf(m < 9950 ? 2 : 1).format(m / 1000)} ${t('unit.km')}`;
}

export const fmtNum = (n) => (Number.isFinite(n) ? nf(0).format(Math.round(n)) : '–');

export function fmtEle(m) {
  return Number.isFinite(m) ? `${nf(0).format(Math.round(m))} ${t('unit.m')}` : '–';
}

export function fmtTime(s) {
  if (!Number.isFinite(s)) return '–';
  const min = Math.max(1, Math.round(s / 60));
  if (min < 60) return `${min} ${t('unit.min')}`;
  const h = Math.floor(min / 60), m = min % 60;
  return m ? `${h} ${t('unit.h')} ${m} ${t('unit.min')}` : `${h} ${t('unit.h')}`;
}

// ---------------------------------------------------------------- the public site's own strings
// (Georgian here was written by Claude — have a native speaker check it.)
Object.assign(en, {
  'app.title': 'Stylized Maps',
  'site.home': 'All maps',
  'state.unreachable.title': 'The site isn’t answering',
  'state.unreachable.body': 'Check your connection and try again.',
  'state.notDrawn.body': 'Drawing it takes a few seconds.',
  'save.errorToast': 'Your additions couldn’t be saved. Check your connection.',
  'prep.title': 'Preparing {name}',
  'prep.queued': 'Waiting in line for the map data.',
  'prep.fetching': 'Downloading OpenStreetMap data and elevation. When the OSM servers are busy this can take several minutes.',
  'prep.drawing': 'Drawing the first map…',
  'prep.position': 'Number {n} in line',
  'prep.leave': 'You can close this page and come back later — the map keeps being made.',
  'prep.failed': 'This map couldn’t be made',
  'prep.back': 'Back to all maps',
  'prep.notFound': 'There is no such map',
  'quota.title': 'Not drawn',
  'export.jpg': 'JPG preview',
  'export.pngSize': '3000 px wide',
  'auth.signIn': 'Sign in with Google',
  'auth.signOut': 'Sign out',
  'auth.myMaps': 'My maps',
  'auth.admin': 'Admin panel',
  'auth.toAdd': 'Sign in to add places, paths and notes.',
  'auth.notConfigured': 'Sign-in is not set up on this server yet.',
  'share.tip': 'Suggest for the public map',
  'share.pending': 'Waiting for review — click to send your latest version',
  'share.approved': 'On the public map',
  'share.rejected': 'Not accepted for the public map — click to suggest it again',
  'share.sent': 'Sent for review. It appears on the public map once approved.',
  'share.updated': 'Your suggestion was updated.',
  'share.failed': 'It could not be sent.',
  'share.again': 'This is already on the public map. Suggest the changed version?',
  'home.title': 'Illustrated maps of real places',
  'home.lead': 'Type a village, town or valley. It is drawn from OpenStreetMap — trees, slopes, rivers, little houses. Add your own places and paths, then download a poster.',
  'home.search.ph': 'e.g. Mestia, Georgia',
  'home.search.go': 'Find',
  'home.searching': 'Searching…',
  'home.noResults': 'Nothing found. Try adding the region or country.',
  'home.searchFailed': 'The place search isn’t answering. Try again in a moment.',
  'home.pick': 'Which one?',
  'home.size': 'Area',
  'home.size.s': 'Small · 1.6 km',
  'home.size.m': 'Medium · 2.8 km',
  'home.size.l': 'Large · 4.4 km',
  'home.lang': 'Map language',
  'home.make': 'Make the map',
  'home.making': 'Starting…',
  'home.left': '{n} new maps left today',
  'home.signToMake': 'Sign in with Google to make a new map. Looking at maps and downloading them needs no account.',
  'home.gallery': 'Maps made so far',
  'home.mine': 'My maps',
  'home.filter.ph': 'Filter by name',
  'home.more': 'Show more',
  'home.empty': 'No maps yet — make the first one.',
  'home.mineEmpty': 'You haven’t made or edited a map yet.',
  'home.credit': 'Map data © OpenStreetMap contributors · Elevation: Mapzen / AWS Terrain Tiles',
  'home.login.failed': 'Sign-in didn’t work: {why}',
  'home.login.banned': 'This account is blocked.',
  'home.uiLang': 'Language',
  'langname.en': 'English', 'langname.ka': 'Georgian', 'langname.de': 'German',
});
Object.assign(ka, {
  'app.title': 'სტილიზებული რუკები',
  'site.home': 'ყველა რუკა',
  'state.unreachable.title': 'საიტი არ პასუხობს',
  'state.unreachable.body': 'შეამოწმეთ ინტერნეტთან კავშირი და სცადეთ ხელახლა.',
  'state.notDrawn.body': 'დახატვას რამდენიმე წამი სჭირდება.',
  'save.errorToast': 'თქვენი დამატებები ვერ შეინახა. შეამოწმეთ ინტერნეტთან კავშირი.',
  'prep.title': '{name} — რუკა მზადდება',
  'prep.queued': 'რუკის მონაცემები რიგში დგას.',
  'prep.fetching': 'იტვირთება OpenStreetMap-ის მონაცემები და რელიეფი. თუ OSM-ის სერვერები გადატვირთულია, ამას რამდენიმე წუთი შეიძლება დასჭირდეს.',
  'prep.drawing': 'პირველი რუკა იხატება…',
  'prep.position': 'რიგში ხართ {n}-ე',
  'prep.leave': 'შეგიძლიათ დახუროთ გვერდი და მოგვიანებით დაბრუნდეთ — რუკა მაინც მომზადდება.',
  'prep.failed': 'ამ რუკის შექმნა ვერ მოხერხდა',
  'prep.back': 'ყველა რუკაზე დაბრუნება',
  'prep.notFound': 'ასეთი რუკა არ არსებობს',
  'quota.title': 'არ დაიხატა',
  'export.jpg': 'JPG, გადასახედად',
  'export.pngSize': 'სიგანე 3000 px',
  'auth.signIn': 'Google-ით შესვლა',
  'auth.signOut': 'გასვლა',
  'auth.myMaps': 'ჩემი რუკები',
  'auth.admin': 'ადმინისტრირება',
  'auth.toAdd': 'ადგილების, ბილიკებისა და მინაწერების დასამატებლად შედით ანგარიშზე.',
  'auth.notConfigured': 'ამ სერვერზე შესვლა ჯერ არ არის გამართული.',
  'share.tip': 'საჯარო რუკაზე დამატების შეთავაზება',
  'share.pending': 'განხილვას ელოდება — დააჭირეთ ბოლო ვერსიის გასაგზავნად',
  'share.approved': 'საჯარო რუკაზეა',
  'share.rejected': 'საჯარო რუკაზე არ დაემატა — დააჭირეთ ხელახლა შესათავაზებლად',
  'share.sent': 'გაიგზავნა განსახილველად. დამტკიცების შემდეგ საჯარო რუკაზე გამოჩნდება.',
  'share.updated': 'შეთავაზება განახლდა.',
  'share.failed': 'გაგზავნა ვერ მოხერხდა.',
  'share.again': 'ეს უკვე საჯარო რუკაზეა. შევთავაზოთ შეცვლილი ვერსია?',
  'home.title': 'რეალური ადგილების ილუსტრირებული რუკები',
  'home.lead': 'ჩაწერეთ სოფლის, ქალაქის ან ხეობის სახელი. რუკა OpenStreetMap-ის მონაცემებით დაიხატება — ხეებით, ფერდობებით, მდინარეებითა და პატარა სახლებით. დაამატეთ თქვენი ადგილები და ბილიკები და ჩამოტვირთეთ პოსტერი.',
  'home.search.ph': 'მაგ.: მესტია, საქართველო',
  'home.search.go': 'ძებნა',
  'home.searching': 'ვეძებთ…',
  'home.noResults': 'ვერაფერი მოიძებნა. მიუთითეთ რეგიონი ან ქვეყანაც.',
  'home.searchFailed': 'ადგილების ძებნა არ პასუხობს. ცოტა ხანში სცადეთ.',
  'home.pick': 'რომელი?',
  'home.size': 'ფართობი',
  'home.size.s': 'პატარა · 1,6 კმ',
  'home.size.m': 'საშუალო · 2,8 კმ',
  'home.size.l': 'დიდი · 4,4 კმ',
  'home.lang': 'რუკის ენა',
  'home.make': 'რუკის შექმნა',
  'home.making': 'ვიწყებთ…',
  'home.left': 'დღეს კიდევ {n} ახალი რუკის შექმნა შეგიძლიათ',
  'home.signToMake': 'ახალი რუკის შესაქმნელად შედით Google-ით. რუკების დათვალიერებასა და ჩამოტვირთვას ანგარიში არ სჭირდება.',
  'home.gallery': 'უკვე შექმნილი რუკები',
  'home.mine': 'ჩემი რუკები',
  'home.filter.ph': 'ფილტრი სახელით',
  'home.more': 'მეტის ჩვენება',
  'home.empty': 'რუკები ჯერ არ არის — შექმენით პირველი.',
  'home.mineEmpty': 'ჯერ არცერთი რუკა არ შეგიქმნიათ და არ შეგიცვლიათ.',
  'home.credit': 'რუკის მონაცემები © OpenStreetMap-ის მონაწილეები · რელიეფი: Mapzen / AWS Terrain Tiles',
  'home.login.failed': 'შესვლა ვერ მოხერხდა: {why}',
  'home.login.banned': 'ეს ანგარიში დაბლოკილია.',
  'home.uiLang': 'ენა',
  'langname.en': 'ინგლისური', 'langname.ka': 'ქართული', 'langname.de': 'გერმანული',
});
