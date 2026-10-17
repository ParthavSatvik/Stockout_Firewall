"""Native-script product aliases (Kannada, Hindi, Tamil, Telugu, Bengali) for the order
parser. Seeded for demo data and inserted into existing databases by migration."""

NATIVE_SCRIPT_ALIASES: dict[str, list[tuple[str, str]]] = {
    'Rice': [('ಅಕ್ಕಿ', 'kn'), ('चावल', 'hi'), ('அரிசி', 'ta'), ('బియ్యం', 'te'), ('চাল', 'bn')],
    'Wheat Atta': [('ಗೋಧಿ ಹಿಟ್ಟು', 'kn'), ('आटा', 'hi'), ('கோதுமை மாவு', 'ta'), ('గోధుమ పిండి', 'te'), ('আটা', 'bn')],
    'Toor Dal': [('ತೊಗರಿ ಬೇಳೆ', 'kn'), ('तूर दाल', 'hi'), ('अरहर दाल', 'hi'), ('துவரம் பருப்பு', 'ta'), ('కంది పప్పు', 'te'), ('অড়হর ডাল', 'bn')],
    'Moong Dal': [('ಹೆಸರು ಬೇಳೆ', 'kn'), ('मूंग दाल', 'hi'), ('பாசிப் பருப்பு', 'ta'), ('పెసర పప్పు', 'te'), ('মুগ ডাল', 'bn')],
    'Sugar': [('ಸಕ್ಕರೆ', 'kn'), ('चीनी', 'hi'), ('சர்க்கரை', 'ta'), ('చక్కెర', 'te'), ('চিনি', 'bn')],
    'Sunflower Oil': [('ಎಣ್ಣೆ', 'kn'), ('तेल', 'hi'), ('எண்ணெய்', 'ta'), ('నూనె', 'te'), ('তেল', 'bn')],
    'Salt': [('ಉಪ್ಪು', 'kn'), ('नमक', 'hi'), ('உப்பு', 'ta'), ('ఉప్పు', 'te'), ('লবণ', 'bn')],
    'Besan': [('ಕಡಲೆ ಹಿಟ್ಟು', 'kn'), ('बेसन', 'hi'), ('கடலை மாவு', 'ta'), ('శనగ పిండి', 'te'), ('বেসন', 'bn')],
    'Tea Powder': [('ಚಹಾ ಪುಡಿ', 'kn'), ('चाय पत्ती', 'hi'), ('டீ தூள்', 'ta'), ('టీ పొడి', 'te'), ('চা পাতা', 'bn')],
}
