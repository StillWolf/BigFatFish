import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from bilibili_social import Social


class FakeAPI:
    def __init__(self): self.sent=[]; self.fail=False; self.follower_data={'list':[{'mid':301,'uname':'粉丝'}], 'total':21}; self.get_urls=[]
    async def nav(self): return {'isLogin':True,'mid':100,'wbi_img':{'img_url':'https://example.test/'+('a'*32)+'.png','sub_url':'https://example.test/'+('b'*32)+'.png'}}
    def canonical_video(self,v): return (v,'https://www.bilibili.com/video/'+v)
    async def api(self,method,url,**kw):
        if method=='get': self.get_urls.append(url)
        if method=='post':
            self.sent.append({'url':url,'form':kw['form']})
            if self.fail:raise TimeoutError()
            return {'code':0,'data':{}}
        if '/get_sessions?' in url:
            return {'code':0,'data':{'session_list':[{'session_type':1,'talker_id':200,'unread_count':1,'max_seqno':123,
                'last_msg':{'sender_uid':200,'msg_key':'900000000000000001'},'account_info':{'name':'测试用户'}}]}}
        if '/fetch_session_msgs?' in url:
            return {'code':0,'data':{'messages':[{'msg_type':1,'msg_status':0,'sender_uid':200,'timestamp':1,'content':'{"content":"你好"}'},
                {'msg_type':1,'msg_status':1,'sender_uid':200,'timestamp':2,'content':'{"content":"已撤回"}'}]}}
        if '/followings?' in url:return {'code':0,'data':{'list':[{'mid':300,'uname':'作者'}]}}
        if '/followers?' in url:return {'code':0,'data':self.follower_data}
        if '/x/msgfeed/reply?' in url:return {'code':0,'data':{'items':[{'user':{'mid':301,'nickname':'回复者'},
            'item':{'source_content':'你好','target_reply_content':'原评论','title':'视频标题'},'reply_time':123}]}}
        if '/x/web-interface/search/type?' in url:return {'code':0,'data':{'result':[{'mid':401,
            'uname':'<em class="keyword">作者</em>','usign':'签名','fans':3}]}}
        if '/view?' in url:return {'code':0,'data':{'owner':{'mid':400,'name':'作者'}}}
        if '/arc/search?' in url:return {'code':0,'data':{'list':{'vlist':[{'bvid':'BV1234567890','title':'视频'}]}}}
        raise AssertionError(url)


class SocialTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)/'bili';self.root.mkdir();self.project=Path(self.tmp.name)/'project';self.api=FakeAPI()
        async def cookies(_):return [{'name':'bili_jct','value':'secret'}]
        browser=SimpleNamespace(comments=self.api,context=SimpleNamespace(cookies=cookies),seen={'BV1234567890'})
        self.social=Social(browser,self.root,self.project)
    def tearDown(self):self.tmp.cleanup()
    def enable(self):(self.root/'social-enabled').write_text('1')

    async def test_direct_reply_not_proactive_limited_and_no_duplicate(self):
        self.enable();await self.social.list_sessions()
        result=await self.social.send('200','你好')
        self.assertTrue(result['submitted']);self.assertEqual(self.api.sent[0]['form']['msg[receiver_id]'],'200')
        with self.assertRaisesRegex(ValueError,'已处理'):await self.social.send('200','你好')
        self.assertEqual(len(self.api.sent),1)

    async def test_private_read_filters_recalled_messages(self):
        self.enable();sessions=await self.social.list_sessions()
        self.assertNotIn('你好',json.dumps(sessions,ensure_ascii=False))
        result=await self.social.messages('200')
        self.assertEqual([x['text'] for x in result['messages']],['你好'])

    async def test_unknown_result_cannot_be_retried(self):
        self.enable();await self.social.list_sessions();self.api.fail=True
        with self.assertRaisesRegex(ValueError,'结果未知'):await self.social.send('200','你好')
        with self.assertRaisesRegex(ValueError,'已处理'):await self.social.send('200','你好')
        self.assertEqual(len(self.api.sent),1)

    async def test_follow_and_view_followed_creator(self):
        self.enable();users=await self.social.followings();self.assertEqual(users['users'][0]['uid'],'300')
        videos=await self.social.videos('300');self.assertTrue(videos['videos'][0]['previouslyWatched'])
        author=await self.social.creator('BV1234567890');self.assertTrue(author['watched'])
        self.assertTrue((await self.social.follow('400'))['submitted'])
        self.assertEqual(self.api.sent[0]['form']['act'],'1')

    async def test_own_followers_are_paginated_and_available_as_known_users(self):
        result=await self.social.followers(limit=20,page=1)
        self.assertEqual(result['users'][0]['uid'],'301')
        self.assertEqual(result['total'],21);self.assertTrue(result['hasMore'])
        self.assertIn('vmid=100',self.api.get_urls[-1]);self.assertIn('pn=1',self.api.get_urls[-1])
        self.assertIn('301',self.social.known)

    async def test_missing_follower_list_is_not_reported_as_empty(self):
        self.api.follower_data={'list':[],'total':2}
        with self.assertRaisesRegex(ValueError,'未返回名单'):await self.social.followers()

    async def test_search_user_returns_compact_name_and_enables_follow(self):
        self.enable(); result=await self.social.users('作者')
        self.assertEqual(result['users'][0]['name'],'作者')
        self.assertEqual(result['users'][0]['uid'],'401')
        self.assertTrue((await self.social.follow('401'))['submitted'])

    async def test_reply_feed_returns_original_and_reply_without_posting(self):
        result=await self.social.replies()
        self.assertEqual(result['replies'][0]['theirReply'],'你好')
        self.assertEqual(result['replies'][0]['myComment'],'原评论')
        self.assertEqual(self.api.sent,[])

    async def test_disabled_and_unknown_recipient_do_not_send(self):
        with self.assertRaisesRegex(ValueError,'尚未启用'):await self.social.send('200','你好')
        self.enable()
        with self.assertRaisesRegex(ValueError,'请先查看'):await self.social.send('200','你好')
        self.assertEqual(self.api.sent,[])

    async def test_incoming_queue_idempotent_and_contains_no_message_text(self):
        self.enable();folder=self.project/'data/qq-bridge';folder.mkdir(parents=True)
        (folder/'qq-runtime.json').write_text(json.dumps({'pid':os.getpid(),'updatedAt':time.time()*1000}))
        self.assertTrue(self.social.enqueue_incoming('200','42'))
        self.assertFalse(self.social.enqueue_incoming('200','42'))
        rows=(folder/'qq-inject.jsonl').read_text().splitlines();self.assertEqual(len(rows),1)
        self.assertNotIn('你好',rows[0]);self.assertEqual(json.loads(rows[0])['label'],'B站私信')


if __name__=='__main__':unittest.main()
